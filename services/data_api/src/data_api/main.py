"""data-api application. Phase 0 exposes only tenant introspection; data routes arrive from Phase 1."""

from __future__ import annotations

import base64
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Annotated

import uvicorn
from fastapi import Depends, FastAPI, Header, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import text

from data_api.settings import DataSettings, get_settings
from data_api.tenancy import ControlReader, TenantPools, tenant_schemas, vault_password_resolver
from dcs_authz import Policy, default_policy
from dcs_common import context
from dcs_common.auth import JwksCache, Principal, TokenError, TokenValidator, bearer_from_header
from dcs_common.logging import configure_logging
from dcs_common.problem import (
    PROBLEM_RESPONSES,
    ProblemError,
    forbidden,
    mfa_required,
    not_found,
    unauthorized,
)
from dcs_common.telemetry import setup_telemetry
from dcs_common.tenant import TenantContext
from dcs_common.web import install_common
from dcs_vault import AwsKmsKeyService, KeyService, LocalKeyService, Vault


@dataclass
class DataState:
    settings: DataSettings
    validator: TokenValidator
    reader: ControlReader
    pools: TenantPools
    policy: Policy = field(default_factory=default_policy)

    async def close(self) -> None:
        await self.pools.dispose()
        await self.reader.dispose()


def build_state(settings: DataSettings) -> DataState:
    keys: KeyService
    if settings.key_service == "aws":
        keys = AwsKmsKeyService.from_region(settings.aws_region)
    else:
        keys = LocalKeyService(
            base64.b64decode(settings.local_master_key.get_secret_value()), Path(settings.local_key_dir)
        )
    reader = ControlReader(settings.control_reader_url.get_secret_value())
    pools = TenantPools(
        settings.tenant_db_host,
        settings.tenant_db_port,
        vault_password_resolver(reader, Vault(keys)),
        pool_size=settings.tenant_pool_size,
        max_pools=settings.max_tenant_pools,
    )
    return DataState(settings, TokenValidator(settings.issuers(), JwksCache()), reader, pools)


# ------------------------------------------------------------------------------------------ deps
def get_state(request: Request) -> DataState:
    state: DataState = request.app.state.dcs
    return state


StateDep = Annotated[DataState, Depends(get_state)]


async def principal(request: Request, state: StateDep) -> Principal:
    try:
        p = await state.validator.validate(bearer_from_header(request.headers.get("authorization")))
    except TokenError as exc:
        raise unauthorized(str(exc)) from None
    if p.is_staff:
        raise forbidden("Staff tokens cannot read tenant data (break-glass is required).")
    return p


@dataclass(frozen=True)
class RequestTenant:
    tenant: TenantContext
    role: str
    permissions: frozenset[str]
    cbm_version: str | None = None


async def tenant_context(
    state: StateDep,
    p: Annotated[Principal, Depends(principal)],
    x_dcs_org: Annotated[str | None, Header(alias="X-DCS-Org")] = None,
) -> RequestTenant:
    """The ONLY way a route obtains a TenantContext (SPEC §8.2)."""
    if not x_dcs_org:
        raise ProblemError(400, slug="org-required", detail="Send the active organisation in X-DCS-Org.")
    try:
        org_id = uuid.UUID(x_dcs_org)
    except ValueError:
        raise not_found() from None
    user_id = await state.reader.user_id_for_subject(p.subject)
    if user_id is None:
        raise not_found()
    m = await state.reader.membership(org_id, user_id)
    if m is None or m.org_status == "deleted":
        raise not_found()
    if m.db_status != "ready":
        raise ProblemError(409, slug="tenant-not-ready", detail="The workspace is still being provisioned.")
    if state.settings.mfa_enforce and state.policy.mfa_required(m.role) and not p.has_mfa():
        raise mfa_required()
    context.org_id_var.set(str(org_id))
    context.tenant_id_var.set(m.tenant.tenant_id)
    return RequestTenant(m.tenant, m.role, state.policy.permissions_for(m.role), m.cbm_version)


TenantDep = Annotated[RequestTenant, Depends(tenant_context)]


# ---------------------------------------------------------------------------------------- routes
class TenantInfo(BaseModel):
    tenant_id: str
    database: str
    db_user: str
    cbm_version: str | None
    schemas: list[str]


def create_app(settings: DataSettings | None = None, state: DataState | None = None) -> FastAPI:
    settings = settings or get_settings()
    app_state = state or build_state(settings)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield
        await app_state.close()

    app = FastAPI(title="DCS-PIS data-api", version="0.0.1", lifespan=lifespan)
    app.state.dcs = app_state
    install_common(app, hsts=True)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST", "PUT"],
        allow_headers=["Authorization", "Content-Type", "X-DCS-Org", "Idempotency-Key"],
    )

    @app.get(
        "/v1/tenant",
        response_model=TenantInfo,
        responses=PROBLEM_RESPONSES,
        tags=["tenant"],
        summary="The tenant database behind the active org (proves TenantContext routing)",
    )
    async def tenant_info(t: TenantDep, s: StateDep) -> TenantInfo:
        if "org:read" not in t.permissions:
            raise forbidden(permission="org:read")
        async with s.pools.connect(t.tenant) as conn:
            db, user = (await conn.execute(text("SELECT current_database(), current_user"))).one()
            t.tenant.assert_database(db)
            schemas = await tenant_schemas(conn)
        return TenantInfo(
            tenant_id=t.tenant.tenant_id,
            database=db,
            db_user=user,
            cbm_version=t.cbm_version,
            schemas=[x for x in schemas if x != "public"],
        )

    return app


def build() -> FastAPI:
    settings = get_settings()
    configure_logging("data-api", settings.log_level)
    app = create_app(settings)
    setup_telemetry(settings, "data-api", app)
    return app


def run() -> None:
    uvicorn.run("data_api.main:build", factory=True, host="0.0.0.0", port=8000, proxy_headers=True)  # noqa: S104


if __name__ == "__main__":
    run()
