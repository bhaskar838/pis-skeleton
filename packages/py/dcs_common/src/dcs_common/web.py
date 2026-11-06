"""Common FastAPI app wiring: problem handlers, security headers, request IDs, health endpoints."""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from dcs_common import context
from dcs_common.problem import install_problem_handlers
from dcs_common.security_headers import SecurityHeadersMiddleware

ReadyCheck = Callable[[], Awaitable[bool]]


class RequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        incoming = request.headers.get("x-request-id", "")
        rid = (
            incoming if 8 <= len(incoming) <= 64 and incoming.replace("-", "").isalnum() else uuid.uuid4().hex
        )
        with context.bind(request_id=rid):
            response = await call_next(request)
        response.headers["x-request-id"] = rid
        return response


def install_common(app: FastAPI, *, hsts: bool = True, ready_check: ReadyCheck | None = None) -> None:
    install_problem_handlers(app)
    app.add_middleware(RequestIdMiddleware)
    app.add_middleware(SecurityHeadersMiddleware, hsts=hsts)

    @app.get("/healthz", include_in_schema=False)
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/readyz", include_in_schema=False)
    async def readyz(response: Response) -> dict[str, str]:
        if ready_check is not None and not await ready_check():
            response.status_code = 503
            return {"status": "not-ready"}
        return {"status": "ready"}
