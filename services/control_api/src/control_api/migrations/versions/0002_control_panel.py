"""Control panel (Phase 0.5, ADR-0011 / ADR-0012): regions, countries, platform settings and sealed secrets.

* ``region`` / ``country``: the editable world map. Readable in every scope (sign-up needs it); written only in
  platform scope (staff routes).
* ``platform_setting`` (+ append-only ``platform_setting_history``): operator-owned values set in the panel.
* ``platform_secret``: write-only secrets, sealed with the platform key (``dcs_vault``). Platform scope only.

The seed is ``control_api.world`` as of this revision. Later changes to the default map need a new migration;
the live map is whatever staff set in the panel.

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-11
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

from control_api.world import COUNTRIES, LAUNCH_COUNTRIES, REGIONS

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

PLATFORM = "current_setting('app.scope', true) = 'platform'"

TABLES_SQL = """
CREATE TABLE region (
    code        text PRIMARY KEY CHECK (code ~ '^[a-z]{2}(-gov)?-[a-z]+-[0-9]$'),
    name        text NOT NULL CHECK (length(name) BETWEEN 1 AND 60),
    status      text NOT NULL CHECK (status IN ('active','planned','disabled')),
    sort        integer NOT NULL DEFAULT 100,
    updated_by  text,
    updated_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE country (
    code            text PRIMARY KEY CHECK (code ~ '^[A-Z]{2}$'),
    name            text NOT NULL CHECK (length(name) BETWEEN 1 AND 80),
    region_code     text NOT NULL REFERENCES region(code),
    signup_enabled  boolean NOT NULL DEFAULT false,
    updated_by      text,
    updated_at      timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX country_region_idx ON country (region_code);

ALTER TABLE org ADD CONSTRAINT org_region_fk FOREIGN KEY (region) REFERENCES region(code);

CREATE TABLE platform_setting (
    key         text PRIMARY KEY,
    value       jsonb NOT NULL,
    version     integer NOT NULL CHECK (version > 0),
    updated_by  text NOT NULL,
    updated_at  timestamptz NOT NULL
);

CREATE TABLE platform_setting_history (
    id          bigserial PRIMARY KEY,
    key         text NOT NULL,
    version     integer NOT NULL CHECK (version > 0),
    action      text NOT NULL CHECK (action IN ('set','reset','revert','secret_set','secret_cleared')),
    value       jsonb,
    changed_by  text NOT NULL,
    changed_at  timestamptz NOT NULL,
    UNIQUE (key, version)
);

CREATE TABLE platform_secret (
    key          text PRIMARY KEY,
    ciphertext   bytea NOT NULL,
    nonce        bytea NOT NULL,
    key_ref      text NOT NULL,
    wrapped_dek  bytea NOT NULL,
    version      integer NOT NULL CHECK (version > 0),
    updated_by   text NOT NULL,
    updated_at   timestamptz NOT NULL
);
"""


def _read_all_write_platform(table: str) -> str:
    return (
        f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;\n"
        f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY;\n"
        f"CREATE POLICY {table}_read ON {table} FOR SELECT USING (true);\n"
        f"CREATE POLICY {table}_insert ON {table} FOR INSERT WITH CHECK ({PLATFORM});\n"
        f"CREATE POLICY {table}_update ON {table} FOR UPDATE USING ({PLATFORM}) WITH CHECK ({PLATFORM});\n"
        f"CREATE POLICY {table}_delete ON {table} FOR DELETE USING ({PLATFORM});\n"
    )


def _platform_only(table: str) -> str:
    return (
        f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;\n"
        f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY;\n"
        f"CREATE POLICY {table}_scope ON {table} USING ({PLATFORM}) WITH CHECK ({PLATFORM});\n"
    )


RLS_SQL = "\n".join(
    [
        _read_all_write_platform("region"),
        _read_all_write_platform("country"),
        _read_all_write_platform("platform_setting"),
        _platform_only("platform_setting_history"),
        _platform_only("platform_secret"),
    ]
)

GRANTS_SQL = """
GRANT SELECT, INSERT, UPDATE, DELETE ON region, country, platform_setting, platform_secret TO dcs_control_app;
GRANT SELECT, INSERT ON platform_setting_history TO dcs_control_app;
GRANT USAGE, SELECT ON SEQUENCE platform_setting_history_id_seq TO dcs_control_app;
GRANT SELECT ON region, country TO dcs_control_reader;
"""


def upgrade() -> None:
    op.execute(TABLES_SQL)
    bind = op.get_bind()
    bind.execute(
        sa.text("INSERT INTO region (code, name, status, sort, updated_by) VALUES (:c, :n, :s, :o, 'seed')"),
        [{"c": c, "n": n, "s": s, "o": o} for c, n, s, o in REGIONS],
    )
    bind.execute(
        sa.text(
            "INSERT INTO country (code, name, region_code, signup_enabled, updated_by) "
            "VALUES (:c, :n, :r, :e, 'seed')"
        ),
        [{"c": c, "n": n, "r": r, "e": c in LAUNCH_COUNTRIES} for c, (n, r) in COUNTRIES.items()],
    )
    op.execute(RLS_SQL)
    op.execute(GRANTS_SQL)


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE org DROP CONSTRAINT IF EXISTS org_region_fk;
        DROP TABLE IF EXISTS platform_secret, platform_setting_history, platform_setting, country, region CASCADE;
        """
    )
