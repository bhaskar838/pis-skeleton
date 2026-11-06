"""Cluster bootstrap + Control DB migrations. Idempotent; run by the ``control-migrate`` one-shot container.

Creates the Control DB roles and database if missing, then applies Alembic migrations as the owner role:

* ``dcs_control_owner``  owns ``dcs_control``; runs migrations.
* ``dcs_control_app``    control-api + control-worker (NOBYPASSRLS; DML only).
* ``dcs_control_reader`` data-api (SELECT on a few tables; may read only tenant ``_ro`` credentials).

Usage: ``python -m control_api.bootstrap`` with ``DCS_TENANT_ADMIN_URL`` and the three role passwords in
``DCS_CONTROL_OWNER_PASSWORD`` / ``DCS_CONTROL_APP_PASSWORD`` / ``DCS_CONTROL_READER_PASSWORD``.
"""

from __future__ import annotations

import asyncio
import os
from importlib import resources
from urllib.parse import quote, urlsplit, urlunsplit

import asyncpg
from alembic import command
from alembic.config import Config

from dcs_common.sqlident import ident
from dcs_common.sqlident import literal as sql_literal

CONTROL_DB = "dcs_control"
ROLES = ("dcs_control_owner", "dcs_control_app", "dcs_control_reader")


def _with_db(
    url: str, db: str, *, user: str | None = None, password: str | None = None, driver: str = ""
) -> str:
    parts = urlsplit(url)
    host = parts.hostname or "localhost"
    port = f":{parts.port}" if parts.port else ""
    u = user or parts.username or "postgres"
    p = password if password is not None else (parts.password or "")
    auth = f"{quote(u)}:{quote(p)}@" if p else f"{quote(u)}@"
    scheme = "postgresql" + (f"+{driver}" if driver else "")
    return urlunsplit((scheme, f"{auth}{host}{port}", f"/{db}", "", ""))


async def ensure_roles_and_db(admin_url: str, passwords: dict[str, str]) -> None:
    conn = await asyncpg.connect(_with_db(admin_url, "postgres"))
    try:
        for role in ROLES:
            pw = passwords[role]
            exists = await conn.fetchval("SELECT 1 FROM pg_roles WHERE rolname = $1", role)
            verb = "ALTER" if exists else "CREATE"
            await conn.execute(
                f"{verb} ROLE {ident(role)} LOGIN NOSUPERUSER NOBYPASSRLS PASSWORD {sql_literal(pw)}"
            )
        if not await conn.fetchval("SELECT 1 FROM pg_database WHERE datname = $1", CONTROL_DB):
            await conn.execute(f"CREATE DATABASE {ident(CONTROL_DB)} OWNER {ident('dcs_control_owner')}")
        await conn.execute(f"REVOKE ALL ON DATABASE {ident(CONTROL_DB)} FROM PUBLIC")
        for role in ROLES:
            await conn.execute(f"GRANT CONNECT ON DATABASE {ident(CONTROL_DB)} TO {ident(role)}")
    finally:
        await conn.close()


def alembic_config(migrator_sync_url: str) -> Config:
    # Migrations ship inside the package (src/control_api/migrations) so wheels and images carry them.
    cfg = Config()
    cfg.set_main_option("script_location", str(resources.files("control_api") / "migrations"))
    cfg.attributes["sqlalchemy_url"] = migrator_sync_url
    return cfg


def migrate(admin_url: str, owner_password: str, revision: str = "head") -> None:
    url = _with_db(admin_url, CONTROL_DB, user="dcs_control_owner", password=owner_password, driver="psycopg")
    command.upgrade(alembic_config(url), revision)


def downgrade(admin_url: str, owner_password: str, revision: str) -> None:
    url = _with_db(admin_url, CONTROL_DB, user="dcs_control_owner", password=owner_password, driver="psycopg")
    command.downgrade(alembic_config(url), revision)


def ensure_dev_bucket() -> None:
    """Local/CI only: create the data bucket with versioning (prod buckets come from Terraform)."""
    from control_api.infra.objectstore import build_client

    bucket = os.environ.get("DCS_S3_BUCKET", "dcs-data-local")
    client = build_client(
        os.environ.get("DCS_S3_ENDPOINT"),
        os.environ.get("DCS_S3_ACCESS_KEY", ""),
        os.environ.get("DCS_S3_SECRET_KEY", ""),
        os.environ.get("DCS_AWS_REGION", "us-east-1"),
    )
    existing = {b["Name"] for b in client.list_buckets().get("Buckets", [])}
    if bucket not in existing:
        client.create_bucket(Bucket=bucket)
    client.put_bucket_versioning(Bucket=bucket, VersioningConfiguration={"Status": "Enabled"})


def main() -> None:
    admin_url = os.environ["DCS_TENANT_ADMIN_URL"]
    passwords = {
        "dcs_control_owner": os.environ["DCS_CONTROL_OWNER_PASSWORD"],
        "dcs_control_app": os.environ["DCS_CONTROL_APP_PASSWORD"],
        "dcs_control_reader": os.environ["DCS_CONTROL_READER_PASSWORD"],
    }
    asyncio.run(ensure_roles_and_db(admin_url, passwords))
    migrate(admin_url, passwords["dcs_control_owner"])
    if os.environ.get("DCS_ENV", "local") in ("local", "ci"):
        ensure_dev_bucket()
    print("control db bootstrap: ok")


if __name__ == "__main__":
    main()
