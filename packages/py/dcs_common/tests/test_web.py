from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel
from starlette.exceptions import HTTPException

from dcs_common.problem import (
    PROBLEM_MEDIA_TYPE,
    PROBLEM_RESPONSES,
    ProblemError,
    conflict,
    forbidden,
    mfa_required,
    not_found,
    unauthorized,
)
from dcs_common.settings import DcsSettings
from dcs_common.telemetry import setup_telemetry
from dcs_common.web import install_common


class Body(BaseModel):
    n: int


def _app(ready: bool = True) -> FastAPI:
    app = FastAPI()

    async def check() -> bool:
        return ready

    install_common(app, ready_check=check)

    @app.get("/v1/problem/{kind}", responses=PROBLEM_RESPONSES)
    async def problem(kind: str) -> dict[str, str]:
        errors = {
            "401": unauthorized(),
            "403": forbidden(),
            "404": not_found(),
            "409": conflict("dup", field="slug"),
            "mfa": mfa_required(),
            "418": ProblemError(418, detail="teapot"),
        }
        raise errors[kind]

    @app.get("/v1/http")
    async def http() -> None:
        raise HTTPException(405, "nope")

    @app.post("/v1/body")
    async def body(b: Body) -> Body:
        return b

    @app.get("/v1/crash")
    async def crash() -> None:
        raise RuntimeError("secret detail must not leak")

    return app


@pytest.fixture
def client() -> TestClient:
    return TestClient(_app(), raise_server_exceptions=False)


@pytest.mark.parametrize(
    ("kind", "status", "slug"),
    [
        ("401", 401, "unauthenticated"),
        ("403", 403, "forbidden"),
        ("404", 404, "not-found"),
        ("409", 409, "conflict"),
        ("mfa", 403, "mfa-required"),
        ("418", 418, "error"),
    ],
)
def test_problem_json(client: TestClient, kind: str, status: int, slug: str) -> None:
    r = client.get(f"/v1/problem/{kind}")
    assert r.status_code == status
    assert r.headers["content-type"] == PROBLEM_MEDIA_TYPE
    body = r.json()
    assert body["type"].endswith("/" + slug)
    assert body["status"] == status
    assert body["instance"] == f"/v1/problem/{kind}"


def test_problem_extensions(client: TestClient) -> None:
    assert client.get("/v1/problem/409").json()["field"] == "slug"
    assert client.get("/v1/problem/mfa").json()["step_up_acr"] == "mfa"
    assert client.get("/v1/problem/401").headers["www-authenticate"] == "Bearer"


def test_http_exception_and_404_route(client: TestClient) -> None:
    r = client.get("/v1/http")
    assert r.status_code == 405
    assert r.json()["detail"] == "nope"
    assert client.get("/nope").json()["type"].endswith("/not-found")


def test_validation_error(client: TestClient) -> None:
    r = client.post("/v1/body", json={"n": "x"})
    assert r.status_code == 422
    assert r.json()["errors"][0]["loc"] == ["body", "n"]


def test_unhandled_error_hides_details(client: TestClient) -> None:
    r = client.get("/v1/crash")
    assert r.status_code == 500
    assert "secret" not in r.text
    assert r.json()["type"].endswith("/internal")


def test_security_headers(client: TestClient) -> None:
    r = client.get("/healthz")
    assert r.headers["content-security-policy"].startswith("default-src 'none'")
    assert "max-age=" in r.headers["strict-transport-security"]
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["x-frame-options"] == "DENY"
    api = client.get("/v1/problem/404")
    assert api.headers["cache-control"] == "no-store"
    docs = client.get("/docs")
    assert "cdn.jsdelivr.net" in docs.headers["content-security-policy"]


def test_request_id(client: TestClient) -> None:
    r = client.get("/healthz", headers={"x-request-id": "abcdef123456"})
    assert r.headers["x-request-id"] == "abcdef123456"
    generated = client.get("/healthz", headers={"x-request-id": "bad id!"}).headers["x-request-id"]
    assert generated != "bad id!"
    assert len(generated) == 32


def test_health_and_ready() -> None:
    assert TestClient(_app()).get("/readyz").json() == {"status": "ready"}
    r = TestClient(_app(ready=False)).get("/readyz")
    assert r.status_code == 503


def test_telemetry_setup_is_idempotent() -> None:
    settings = DcsSettings(otel_endpoint="http://127.0.0.1:1")  # exporter never flushes in this test
    app = FastAPI()
    setup_telemetry(settings, "svc", app)
    setup_telemetry(settings, "svc", None)
