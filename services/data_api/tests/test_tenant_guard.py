"""TenantContext guard and per-tenant pools (SPEC §8.2, P0-T10)."""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from data_api.tenancy import TenantPools, install_guard
from dcs_common.tenant import TenantContext, TenantGuardError

pytestmark = pytest.mark.integration


async def test_pool_routes_to_the_tenant_database(control: Any, data: Any) -> None:
    _, org = await control.signup("Pool Co", "IN")
    ctx = TenantContext(uuid.UUID(org["id"]), org["tenant_id"])
    async with data.state.pools.connect(ctx) as conn:
        db, user = (await conn.execute(text("SELECT current_database(), current_user"))).one()
    assert (db, user) == (org["tenant_id"], f"{org['tenant_id']}_ro")
    assert org["tenant_id"] in data.state.pools


async def test_guard_blocks_a_connection_to_another_tenant_db(control: Any, data: Any, cluster: Any) -> None:
    _, a = await control.signup("Guard A", "IN")
    _, b = await control.signup("Guard B", "IN")
    pw_a = await control.state.workflows.activities.role_password(a["id"], a["tenant_id"], "ro")
    # An engine that (wrongly) points at A's database while serving B's context must fail before any query.
    engine = create_async_engine(
        f"postgresql+asyncpg://{a['tenant_id']}_ro:{pw_a}@{cluster.host}:{cluster.port}/{a['tenant_id']}"
    )
    install_guard(engine, TenantContext(uuid.UUID(b["id"]), b["tenant_id"]))
    try:
        with pytest.raises(TenantGuardError):
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
    finally:
        await engine.dispose()


async def test_pool_registry_rejects_a_mismatched_context() -> None:
    async def password(_: TenantContext) -> str:
        return "unused"

    pools = TenantPools("localhost", 1, password)
    ctx = TenantContext(uuid.UUID(int=1), "t_abcdefghij")
    await pools.engine(ctx)  # engine creation is lazy; no connection yet
    with pytest.raises(TenantGuardError):
        await pools.engine(TenantContext(uuid.UUID(int=2), "t_abcdefghij"))
    await pools.dispose()


async def test_pool_lru_eviction() -> None:
    async def password(_: TenantContext) -> str:
        return "unused"

    pools = TenantPools("localhost", 1, password, max_pools=2)
    ids = ["t_aaaaaaaaaa", "t_bbbbbbbbbb", "t_cccccccccc"]
    for i, tid in enumerate(ids):
        await pools.engine(TenantContext(uuid.UUID(int=i + 1), tid))
    assert ids[0] not in pools and ids[2] in pools
    await pools.dispose()


async def test_tenant_not_ready(control: Any, data: Any) -> None:
    """A tenant still provisioning answers 409, not a connection error."""
    control.state.workflows.run_inline = False
    try:
        token, _email = await control.user(mfa=True)
        created = await control.client.post(
            "/v1/orgs", json={"name": "Pending Co", "country": "IN"}, headers=control.auth(token)
        )
    finally:
        control.state.workflows.run_inline = True
    org_id = created.json()["id"]
    r = await data.client.get("/v1/tenant", headers=control.auth(token, org_id))
    assert r.status_code == 409 and r.json()["type"].endswith("/tenant-not-ready")
