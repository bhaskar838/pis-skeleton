"""TenantContext resolution and per-tenant connection pools (SPEC §8.2, ADR-0002).

* The tenant is resolved **only** from the authenticated user's active membership (never from a body or a path).
* Each tenant has its own pool, keyed by tenant ID and connecting as ``<tenant>_ro`` to database ``<tenant>``.
* Guard: every new physical connection records ``current_database()``; every checkout compares it with the
  TenantContext. A mismatch raises :class:`TenantGuardError` before any query runs.
"""

from __future__ import annotations

import asyncio
import uuid
from collections import OrderedDict
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

from sqlalchemy import event, select, text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, create_async_engine
from sqlalchemy.pool import ConnectionPoolEntry

from dcs_authz import Policy
from dcs_common.tenant import TenantContext, TenantGuardError
from dcs_vault import Sealed, Vault
from dcs_vault import TenantKey as VaultTenantKey

PasswordResolver = Callable[[TenantContext], Awaitable[str]]


@dataclass(frozen=True)
class Membership:
    tenant: TenantContext
    user_id: uuid.UUID
    role: str
    org_status: str
    db_status: str
    cbm_version: str | None = None


class ControlReader:
    """Read-only access to the Control DB as ``dcs_control_reader`` (RLS applies)."""

    def __init__(self, url: str) -> None:
        self.engine = create_async_engine(url, pool_size=5, pool_pre_ping=True)

    async def dispose(self) -> None:
        await self.engine.dispose()

    @asynccontextmanager
    async def _scoped(
        self, org_id: uuid.UUID | None, user_id: uuid.UUID | None
    ) -> AsyncIterator[AsyncConnection]:
        async with self.engine.begin() as conn:
            if org_id is not None:
                await conn.execute(text("SELECT set_config('app.org_id', :v, true)"), {"v": str(org_id)})
            if user_id is not None:
                await conn.execute(text("SELECT set_config('app.user_id', :v, true)"), {"v": str(user_id)})
            yield conn

    async def user_id_for_subject(self, subject: str) -> uuid.UUID | None:
        async with self._scoped(None, None) as conn:
            value = await conn.scalar(text("SELECT id FROM app_user WHERE keycloak_sub = :s"), {"s": subject})
        return value if isinstance(value, uuid.UUID) or value is None else uuid.UUID(str(value))

    async def membership(self, org_id: uuid.UUID, user_id: uuid.UUID) -> Membership | None:
        async with self._scoped(org_id, user_id) as conn:
            row = (
                await conn.execute(
                    text(
                        "SELECT m.role, o.tenant_id, o.status AS org_status, d.status AS db_status, d.cbm_version "
                        "FROM membership m JOIN org o ON o.id = m.org_id "
                        "LEFT JOIN tenant_db d ON d.org_id = o.id "
                        "WHERE m.org_id = :o AND m.user_id = :u AND m.status = 'active'"
                    ),
                    {"o": org_id, "u": user_id},
                )
            ).one_or_none()
        if row is None:
            return None
        return Membership(
            TenantContext(org_id, row.tenant_id),
            user_id,
            row.role,
            row.org_status,
            row.db_status or "pending",
            row.cbm_version,
        )

    async def ro_credential(self, ctx: TenantContext) -> tuple[VaultTenantKey, Sealed]:
        async with self._scoped(ctx.org_id, None) as conn:
            key = (
                await conn.execute(
                    text("SELECT kms_key_arn, wrapped_dek FROM tenant_key WHERE org_id = :o"),
                    {"o": ctx.org_id},
                )
            ).one_or_none()
            cred = (
                await conn.execute(
                    text(
                        "SELECT ciphertext, nonce, aad FROM credential WHERE org_id = :o "
                        "AND kind = 'tenant_db_role:ro' AND source_id IS NULL"
                    ),
                    {"o": ctx.org_id},
                )
            ).one_or_none()
        if key is None or cred is None:
            raise TenantGuardError("tenant key or read-only credential missing")
        return (
            VaultTenantKey(ctx.tenant_id, key.kms_key_arn, bytes(key.wrapped_dek)),
            Sealed(bytes(cred.ciphertext), bytes(cred.nonce), cred.aad),
        )


def vault_password_resolver(reader: ControlReader, vault: Vault) -> PasswordResolver:
    async def _resolve(ctx: TenantContext) -> str:
        tkey, sealed = await reader.ro_credential(ctx)
        return (await vault.open(tkey, sealed)).decode()

    return _resolve


def install_guard(engine: AsyncEngine, ctx: TenantContext) -> None:
    sync_engine = engine.sync_engine

    @event.listens_for(sync_engine, "connect")
    def _on_connect(dbapi_conn: Any, record: ConnectionPoolEntry) -> None:
        cur = dbapi_conn.cursor()
        cur.execute("SELECT current_database()")
        record.info["dcs_db"] = cur.fetchone()[0]
        cur.close()

    @event.listens_for(sync_engine, "checkout")
    def _on_checkout(_dbapi_conn: Any, record: ConnectionPoolEntry, _proxy: Any) -> None:
        ctx.assert_database(record.info.get("dcs_db"))


class TenantPools:
    """LRU of per-tenant engines. Pools are keyed by tenant ID only, so a context cannot reach another pool."""

    def __init__(
        self, host: str, port: int, passwords: PasswordResolver, *, pool_size: int = 5, max_pools: int = 200
    ) -> None:
        self._host = host
        self._port = port
        self._passwords = passwords
        self._pool_size = pool_size
        self._max = max_pools
        self._engines: OrderedDict[str, tuple[TenantContext, AsyncEngine]] = OrderedDict()
        self._lock = asyncio.Lock()

    async def engine(self, ctx: TenantContext) -> AsyncEngine:
        async with self._lock:
            hit = self._engines.get(ctx.tenant_id)
            if hit is not None:
                if hit[0] != ctx:
                    raise TenantGuardError("tenant pool registered for a different org")
                self._engines.move_to_end(ctx.tenant_id)
                return hit[1]
            password = await self._passwords(ctx)
            url = (
                f"postgresql+asyncpg://{quote(ctx.role('ro'))}:{quote(password)}@{self._host}:{self._port}/"
                f"{ctx.db_name}"
            )
            engine = create_async_engine(url, pool_size=self._pool_size, max_overflow=0, pool_pre_ping=True)
            install_guard(engine, ctx)
            self._engines[ctx.tenant_id] = (ctx, engine)
            while len(self._engines) > self._max:
                _, (_, old) = self._engines.popitem(last=False)
                await old.dispose()
            return engine

    @asynccontextmanager
    async def connect(self, ctx: TenantContext) -> AsyncIterator[AsyncConnection]:
        engine = await self.engine(ctx)
        async with engine.connect() as conn:
            # Belt and braces: the checkout listener already asserted the DB name.
            yield conn

    async def dispose(self) -> None:
        for _, engine in self._engines.values():
            await engine.dispose()
        self._engines.clear()

    def __contains__(self, tenant_id: object) -> bool:
        return tenant_id in self._engines


async def tenant_schemas(conn: AsyncConnection) -> list[str]:
    rows = await conn.execute(
        select(text("schema_name"))
        .select_from(text("information_schema.schemata"))
        .where(text("schema_name NOT LIKE 'pg\\_%' AND schema_name <> 'information_schema'"))
        .order_by(text("schema_name"))
    )
    return [r[0] for r in rows]


def permissions(policy: Policy, role: str) -> frozenset[str]:
    return policy.permissions_for(role)
