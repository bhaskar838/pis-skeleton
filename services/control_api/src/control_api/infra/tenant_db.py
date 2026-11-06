"""Create / drop tenant databases and their four roles (SPEC §8.1 step 3, ADR-0002). All steps idempotent."""

from __future__ import annotations

import asyncio
from urllib.parse import quote, urlsplit, urlunsplit

import asyncpg

from control_api.infra.scram import scram_sha256_verifier
from dcs_cbm import upgrade_tenant
from dcs_common.ids import is_tenant_id
from dcs_common.sqlident import ident, literal

LOGIN_ROLES = ("owner", "rw", "ro")
EXTENSIONS = ("pgcrypto", "pg_trgm", "vector")


def _admin_dsn(admin_url: str, db: str = "postgres") -> str:
    parts = urlsplit(admin_url.replace("postgresql+asyncpg://", "postgresql://"))
    return urlunsplit((parts.scheme, parts.netloc, f"/{db}", parts.query, ""))


def role_name(tenant_id: str, kind: str) -> str:
    return f"{tenant_id}_{kind}"


def _check(tenant_id: str) -> None:
    if not is_tenant_id(tenant_id):
        raise ValueError(f"invalid tenant id {tenant_id!r}")


async def create_database(admin_url: str, tenant_id: str, passwords: dict[str, str]) -> list[str]:
    """Create roles (owner/rw/ro LOGIN, engine_ro NOLOGIN) and the database. Returns created extensions."""
    _check(tenant_id)
    conn = await asyncpg.connect(_admin_dsn(admin_url))
    try:
        for kind in LOGIN_ROLES:
            role = role_name(tenant_id, kind)
            verifier = scram_sha256_verifier(passwords[kind])
            exists = await conn.fetchval("SELECT 1 FROM pg_roles WHERE rolname = $1", role)
            verb = "ALTER" if exists else "CREATE"
            await conn.execute(
                f"{verb} ROLE {ident(role)} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS "
                f"CONNECTION LIMIT 50 PASSWORD {literal(verifier)}"
            )
        engine = role_name(tenant_id, "engine_ro")
        if not await conn.fetchval("SELECT 1 FROM pg_roles WHERE rolname = $1", engine):
            await conn.execute(f"CREATE ROLE {ident(engine)} NOLOGIN")
        owner = role_name(tenant_id, "owner")
        # The cluster admin must be a member of the owner role to create a DB owned by it (non-superuser admins).
        await conn.execute(f"GRANT {ident(owner)} TO CURRENT_USER")
        if not await conn.fetchval("SELECT 1 FROM pg_database WHERE datname = $1", tenant_id):
            await conn.execute(
                f"CREATE DATABASE {ident(tenant_id)} OWNER {ident(owner)} TEMPLATE template0 ENCODING 'UTF8'"
            )
        await conn.execute(f"REVOKE ALL ON DATABASE {ident(tenant_id)} FROM PUBLIC")
        for kind in ("owner", "rw", "ro"):
            await conn.execute(
                f"GRANT CONNECT ON DATABASE {ident(tenant_id)} TO {ident(role_name(tenant_id, kind))}"
            )
        await conn.execute(f"GRANT CONNECT ON DATABASE {ident(tenant_id)} TO {ident(engine)}")
    finally:
        await conn.close()

    created: list[str] = []
    tconn = await asyncpg.connect(_admin_dsn(admin_url, tenant_id))
    try:
        available = {r["name"] for r in await tconn.fetch("SELECT name FROM pg_available_extensions")}
        for ext in EXTENSIONS:
            if ext in available:
                await tconn.execute(f"CREATE EXTENSION IF NOT EXISTS {ident(ext)}")
                created.append(ext)
        await tconn.execute(f"ALTER SCHEMA public OWNER TO {ident(owner)}")
    finally:
        await tconn.close()
    return created


def tenant_sync_dsn(host: str, port: int, tenant_id: str, kind: str, password: str) -> str:
    return f"postgresql+psycopg://{quote(role_name(tenant_id, kind))}:{quote(password)}@{host}:{port}/{tenant_id}"


async def run_migrations(host: str, port: int, tenant_id: str, owner_password: str) -> None:
    _check(tenant_id)
    dsn = tenant_sync_dsn(host, port, tenant_id, "owner", owner_password)
    await asyncio.to_thread(upgrade_tenant, dsn)


async def drop_database(admin_url: str, tenant_id: str) -> None:
    _check(tenant_id)
    conn = await asyncpg.connect(_admin_dsn(admin_url))
    try:
        if await conn.fetchval("SELECT 1 FROM pg_database WHERE datname = $1", tenant_id):
            await conn.execute(f"ALTER DATABASE {ident(tenant_id)} WITH ALLOW_CONNECTIONS false")
            await conn.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = $1 AND pid <> pg_backend_pid()",
                tenant_id,
            )
            await conn.execute(f"DROP DATABASE IF EXISTS {ident(tenant_id)} WITH (FORCE)")
        for kind in ("engine_ro", "ro", "rw", "owner"):
            role = role_name(tenant_id, kind)
            if await conn.fetchval("SELECT 1 FROM pg_roles WHERE rolname = $1", role):
                await conn.execute(f"DROP ROLE {ident(role)}")
    finally:
        await conn.close()


async def database_exists(admin_url: str, tenant_id: str) -> bool:
    conn = await asyncpg.connect(_admin_dsn(admin_url))
    try:
        return bool(await conn.fetchval("SELECT 1 FROM pg_database WHERE datname = $1", tenant_id))
    finally:
        await conn.close()


async def roles_present(admin_url: str, tenant_id: str) -> list[str]:
    conn = await asyncpg.connect(_admin_dsn(admin_url))
    try:
        rows = await conn.fetch(
            "SELECT rolname FROM pg_roles WHERE rolname LIKE $1 ORDER BY rolname", f"{tenant_id}\\_%"
        )
        return [r["rolname"] for r in rows]
    finally:
        await conn.close()
