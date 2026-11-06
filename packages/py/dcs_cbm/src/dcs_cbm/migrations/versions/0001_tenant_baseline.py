"""Tenant schema baseline (SPEC §8.1 step 4, §11.2).

Creates every tenant schema, the tenant-local audit table and the grants for the four tenant roles. Role names
are derived from ``current_database()`` (the DB name is the tenant ID), so the migration is self-contained.

Grants:
* ``<db>_owner`` owns all schemas (runs migrations).
* ``<db>_rw``    USAGE + DML on every schema except ``engine_api_v1`` (workers).
* ``<db>_ro``    USAGE + SELECT on every schema (data-api reads).
* ``<db>_engine_ro`` USAGE + SELECT on ``engine_api_v1`` only (sandboxed tools).

Revision ID: 0001
Revises:
Create Date: 2026-11-06
"""

from __future__ import annotations

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

SCHEMAS = (
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


def upgrade() -> None:
    schemas_array = "ARRAY[" + ",".join(f"'{s}'" for s in SCHEMAS) + "]"
    op.execute(
        f"""
        DO $$
        DECLARE
            db   text := current_database();
            s    text;
        BEGIN
            FOREACH s IN ARRAY {schemas_array} LOOP
                EXECUTE format('CREATE SCHEMA IF NOT EXISTS %I', s);
                EXECUTE format('REVOKE ALL ON SCHEMA %I FROM PUBLIC', s);
                EXECUTE format('GRANT USAGE ON SCHEMA %I TO %I', s, db || '_ro');
                EXECUTE format('ALTER DEFAULT PRIVILEGES IN SCHEMA %I GRANT SELECT ON TABLES TO %I', s, db || '_ro');
                IF s <> 'engine_api_v1' THEN
                    EXECUTE format('GRANT USAGE ON SCHEMA %I TO %I', s, db || '_rw');
                    EXECUTE format(
                        'ALTER DEFAULT PRIVILEGES IN SCHEMA %I GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO %I',
                        s, db || '_rw');
                    EXECUTE format(
                        'ALTER DEFAULT PRIVILEGES IN SCHEMA %I GRANT USAGE, SELECT ON SEQUENCES TO %I',
                        s, db || '_rw');
                END IF;
            END LOOP;
            EXECUTE format('GRANT USAGE ON SCHEMA engine_api_v1 TO %I', db || '_engine_ro');
            EXECUTE format('ALTER DEFAULT PRIVILEGES IN SCHEMA engine_api_v1 GRANT SELECT ON TABLES TO %I',
                           db || '_engine_ro');
            EXECUTE 'REVOKE CREATE ON SCHEMA public FROM PUBLIC';
        END $$;
        """
    )
    op.execute(
        """
        CREATE TABLE audit_local.event (
            id          bigserial PRIMARY KEY,
            ts          timestamptz NOT NULL DEFAULT now(),
            actor_type  text NOT NULL,
            actor_id    text,
            action      text NOT NULL,
            target_type text,
            target_id   text,
            details     jsonb NOT NULL DEFAULT '{}'::jsonb
        )
        """
    )
    op.execute("CREATE INDEX event_ts_idx ON audit_local.event (ts DESC)")
    op.execute(
        """
        CREATE FUNCTION audit_local.block_mutation() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'audit_local.event is append-only';
        END $$
        """
    )
    op.execute(
        "CREATE TRIGGER event_append_only BEFORE UPDATE OR DELETE ON audit_local.event "
        "FOR EACH ROW EXECUTE FUNCTION audit_local.block_mutation()"
    )
    # Explicit grants for the table created in this migration (default privileges cover later tables).
    op.execute(
        """
        DO $$
        DECLARE db text := current_database();
        BEGIN
            EXECUTE format('GRANT SELECT, INSERT ON audit_local.event TO %I', db || '_rw');
            EXECUTE format('REVOKE UPDATE, DELETE ON audit_local.event FROM %I', db || '_rw');
            EXECUTE format('GRANT USAGE, SELECT ON SEQUENCE audit_local.event_id_seq TO %I', db || '_rw');
            EXECUTE format('GRANT SELECT ON audit_local.event TO %I', db || '_ro');
        END $$;
        """
    )


def downgrade() -> None:
    for s in reversed(SCHEMAS):
        op.execute(f'DROP SCHEMA IF EXISTS "{s}" CASCADE')
