"""Run tenant migrations programmatically (used by ProvisionTenantWorkflow and TenantMigrateWorkflow)."""

from __future__ import annotations

from importlib import resources

from alembic import command
from alembic.config import Config

# "0.0" = Phase 0 schema baseline. Becomes "1.0" when the CBM v1 tables land in Phase 2.
CBM_VERSION = "0.0"

TENANT_SCHEMAS: tuple[str, ...] = (
    "raw_registry",
    "mapping",
    "core",
    "core_quarantine",
    "dq",
    "graph",
    "events",
    "drp",
    "engine_api_v1",
    "results",
    "documents",
    "audit_local",
)


def alembic_config(sync_dsn: str) -> Config:
    """``sync_dsn`` is a SQLAlchemy URL using the psycopg driver, connecting as the tenant ``_owner`` role."""
    cfg = Config()
    cfg.set_main_option("script_location", str(resources.files("dcs_cbm") / "migrations"))
    cfg.attributes["sqlalchemy_url"] = sync_dsn
    return cfg


def upgrade_tenant(sync_dsn: str, revision: str = "head") -> None:
    command.upgrade(alembic_config(sync_dsn), revision)


def downgrade_tenant(sync_dsn: str, revision: str) -> None:
    command.downgrade(alembic_config(sync_dsn), revision)
