"""Shared pytest fixtures for integration and isolation suites (real Postgres + S3 via testcontainers).

Unit tests never touch these fixtures, so ``pytest -m "not integration"`` runs without Docker.
"""

from __future__ import annotations

import os
import secrets
import time
from collections.abc import AsyncIterator, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

# Ryuk (the reaper sidecar) fails to map ports on Docker Desktop for Windows; fixtures clean up themselves.
os.environ.setdefault("TESTCONTAINERS_RYUK_DISABLED", "true")

PG_IMAGE = os.environ.get("DCS_TEST_PG_IMAGE", "pgvector/pgvector:pg16")
# MinIO stopped publishing community images in 2025; RustFS (Apache-2.0) is a drop-in S3 server.
S3_IMAGE = os.environ.get("DCS_TEST_S3_IMAGE", "rustfs/rustfs:latest")


@pytest.fixture(scope="session")
def pg_container() -> Iterator[Any]:
    try:
        from testcontainers.community.postgres import PostgresContainer
    except ImportError:  # older testcontainers
        from testcontainers.postgres import PostgresContainer

    password = secrets.token_urlsafe(12)
    with PostgresContainer(
        PG_IMAGE, username="postgres", password=password, dbname="postgres", driver=None
    ) as pg:
        yield pg


@pytest.fixture(scope="session")
def s3_container() -> Iterator[dict[str, str]]:
    from testcontainers.core.container import DockerContainer
    from testcontainers.core.waiting_utils import wait_for_logs

    user, password = "dcss3test", secrets.token_urlsafe(16)
    container = (
        DockerContainer(S3_IMAGE)
        .with_env("RUSTFS_ACCESS_KEY", user)
        .with_env("RUSTFS_SECRET_KEY", password)
        .with_exposed_ports(9000)
    )
    with container:
        wait_for_logs(container, "Starting", timeout=60)
        endpoint = f"http://{container.get_container_host_ip()}:{container.get_exposed_port(9000)}"
        yield {"endpoint": endpoint, "access_key": user, "secret_key": password}


@pytest.fixture(scope="session")
def s3_client(s3_container: dict[str, str]) -> Any:
    from control_api.infra.objectstore import build_client

    client = build_client(
        s3_container["endpoint"], s3_container["access_key"], s3_container["secret_key"], "us-east-1"
    )
    for attempt in range(30):
        try:
            client.create_bucket(Bucket="dcs-test")
            client.put_bucket_versioning(Bucket="dcs-test", VersioningConfiguration={"Status": "Enabled"})
            break
        except client.exceptions.BucketAlreadyOwnedByYou:
            break
        except Exception:
            if attempt == 29:
                raise
            time.sleep(1)
    return client


@pytest.fixture(scope="session")
async def cluster(pg_container: Any) -> Any:
    from control_api.testing import bootstrap_cluster

    host = pg_container.get_container_host_ip()
    port = int(pg_container.get_exposed_port(5432))
    admin = f"postgresql://postgres:{pg_container.password}@{host}:{port}/postgres"
    return await bootstrap_cluster(admin, host, port)


@pytest.fixture(scope="session")
def tokens() -> Any:
    from control_api.testing import TokenFactory

    return TokenFactory()


@dataclass
class ControlHarness:
    app: Any
    state: Any
    settings: Any
    client: Any
    tokens: Any
    store: Any

    def auth(self, token: str, org_id: str | None = None) -> dict[str, str]:
        headers = {"Authorization": f"Bearer {token}"}
        if org_id:
            headers["X-DCS-Org"] = org_id
        return headers

    async def signup(
        self, name: str = "Northwind Fitness", country: str = "IN"
    ) -> tuple[str, dict[str, Any]]:
        """Create a verified owner with MFA, create an org, and run provisioning inline."""
        from control_api.testing import unique_email

        email = unique_email("owner")
        token = self.tokens.customer(f"sub-{email}", email, mfa=True)
        resp = await self.client.post(
            "/v1/orgs", json={"name": name, "country": country}, headers=self.auth(token)
        )
        assert resp.status_code == 201, resp.text
        return token, resp.json()

    async def user(self, *, mfa: bool = False) -> tuple[str, str]:
        from control_api.testing import unique_email

        email = unique_email("member")
        return self.tokens.customer(f"sub-{email}", email, mfa=mfa), email


@pytest.fixture(scope="session")
async def control(
    cluster: Any, tokens: Any, s3_client: Any, tmp_path_factory: pytest.TempPathFactory
) -> AsyncIterator[ControlHarness]:
    import httpx

    from control_api.main import create_app
    from control_api.testing import build_test_state, make_settings, new_store

    key_dir: Path = tmp_path_factory.mktemp("keys")
    settings = make_settings(cluster, key_dir)
    store = new_store(s3_client, "dcs-test")
    state = build_test_state(settings, tokens, store)
    app = create_app(settings, state)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://control.test") as client:
        yield ControlHarness(app, state, settings, client, tokens, store)
    await state.close()


@dataclass
class DataHarness:
    app: Any
    state: Any
    client: Any


@pytest.fixture(scope="session")
async def data(control: ControlHarness, cluster: Any) -> AsyncIterator[DataHarness]:
    """data-api wired to the same cluster and key directory as the control harness."""
    import base64

    import httpx

    from data_api.main import DataState, create_app
    from data_api.settings import DataSettings
    from data_api.tenancy import ControlReader, TenantPools, vault_password_resolver
    from dcs_vault import LocalKeyService, Vault

    cs = control.settings
    settings = DataSettings(
        env="ci",
        control_reader_url=cluster.control("dcs_control_reader"),
        tenant_db_host=cluster.host,
        tenant_db_port=cluster.port,
        oidc_issuer=cs.oidc_issuer,
        local_master_key=cs.local_master_key,
        local_key_dir=cs.local_key_dir,
    )
    keys = LocalKeyService(base64.b64decode(cs.local_master_key.get_secret_value()), Path(cs.local_key_dir))
    reader = ControlReader(settings.control_reader_url.get_secret_value())
    pools = TenantPools(cluster.host, cluster.port, vault_password_resolver(reader, Vault(keys)), pool_size=2)
    state = DataState(settings, control.tokens.validator(), reader, pools)
    app = create_app(settings, state)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://data.test"
    ) as client:
        yield DataHarness(app, state, client)
    await state.close()
