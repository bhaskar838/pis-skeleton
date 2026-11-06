"""Control DB schema v1 (SPEC §11.1 Phase 0 subset) + row-level security (SPEC §8.2).

RLS model (settings are transaction-local, set by control_api.db):
* ``app.scope = 'platform'``  staff routes and system workflows: see everything.
* ``app.org_id``              the active org of a customer request.
* ``app.user_id``             the calling user (lets ``GET /v1/me`` list the user's own memberships).

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

PLATFORM = "current_setting('app.scope', true) = 'platform'"
ORG = "nullif(current_setting('app.org_id', true), '')::uuid"
USER = "nullif(current_setting('app.user_id', true), '')::uuid"

TABLES_SQL = """
CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS citext;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE TABLE org (
    id               uuid PRIMARY KEY,
    tenant_id        varchar(16) NOT NULL UNIQUE,
    name             text NOT NULL CHECK (length(name) BETWEEN 1 AND 200),
    slug             text NOT NULL UNIQUE,
    country          char(2) NOT NULL,
    region           text NOT NULL,
    status           text NOT NULL DEFAULT 'provisioning'
                     CHECK (status IN ('provisioning','active','failed','deprovisioning','deleted')),
    plan_id          text,
    business_profile jsonb NOT NULL DEFAULT '{}'::jsonb,
    profile_version  integer NOT NULL DEFAULT 1,
    created_by       uuid,
    created_at       timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX org_name_trgm ON org USING gin (name gin_trgm_ops);

-- Prevent region changes after creation (data residency, SPEC §8.7).
CREATE FUNCTION org_region_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.region IS DISTINCT FROM OLD.region OR NEW.tenant_id IS DISTINCT FROM OLD.tenant_id THEN
        RAISE EXCEPTION 'org.region and org.tenant_id are immutable';
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER org_region_immutable BEFORE UPDATE ON org FOR EACH ROW EXECUTE FUNCTION org_region_immutable();

CREATE TABLE app_user (
    id            uuid PRIMARY KEY,
    keycloak_sub  text NOT NULL UNIQUE,
    email         citext NOT NULL UNIQUE,
    name          text,
    created_at    timestamptz NOT NULL DEFAULT now(),
    last_seen_at  timestamptz
);

CREATE TABLE membership (
    id          uuid PRIMARY KEY,
    org_id      uuid NOT NULL REFERENCES org(id) ON DELETE CASCADE,
    user_id     uuid NOT NULL REFERENCES app_user(id) ON DELETE CASCADE,
    role        text NOT NULL CHECK (role IN ('owner','admin','data_manager','analyst','viewer','billing')),
    status      text NOT NULL DEFAULT 'active' CHECK (status IN ('active','removed')),
    invited_by  uuid,
    created_at  timestamptz NOT NULL DEFAULT now(),
    updated_at  timestamptz,
    UNIQUE (org_id, user_id)
);
CREATE INDEX membership_user_idx ON membership (user_id);

CREATE TABLE invite (
    id           uuid PRIMARY KEY,
    org_id       uuid NOT NULL REFERENCES org(id) ON DELETE CASCADE,
    email        citext NOT NULL,
    role         text NOT NULL CHECK (role IN ('owner','admin','data_manager','analyst','viewer','billing')),
    token_hash   bytea NOT NULL UNIQUE,
    status       text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','accepted','revoked')),
    expires_at   timestamptz NOT NULL,
    invited_by   uuid,
    accepted_by  uuid,
    accepted_at  timestamptz,
    created_at   timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX invite_org_idx ON invite (org_id, status);

CREATE TABLE tenant_key (
    org_id                 uuid PRIMARY KEY REFERENCES org(id) ON DELETE CASCADE,
    kms_key_arn            text NOT NULL,
    wrapped_dek            bytea NOT NULL,
    status                 text NOT NULL DEFAULT 'active' CHECK (status IN ('active','pending_deletion')),
    deletion_scheduled_at  timestamptz,
    created_at             timestamptz NOT NULL DEFAULT now(),
    rotated_at             timestamptz
);

CREATE TABLE tenant_db (
    org_id       uuid PRIMARY KEY REFERENCES org(id) ON DELETE CASCADE,
    cluster      text NOT NULL,
    db_name      text NOT NULL UNIQUE,
    status       text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','ready','dropped','failed')),
    cbm_version  text,
    created_at   timestamptz NOT NULL DEFAULT now(),
    updated_at   timestamptz
);

CREATE TABLE credential (
    id          uuid PRIMARY KEY,
    org_id      uuid NOT NULL REFERENCES org(id) ON DELETE CASCADE,
    source_id   uuid,
    kind        text NOT NULL,
    ciphertext  bytea NOT NULL,
    nonce       bytea NOT NULL,
    aad         text NOT NULL,
    expires_at  timestamptz,
    rotated_at  timestamptz,
    created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX credential_org_kind_uq ON credential (org_id, kind) WHERE source_id IS NULL;

CREATE TABLE audit_event (
    id           bigserial PRIMARY KEY,
    ts           timestamptz NOT NULL,
    org_id       uuid,            -- no FK: audit outlives the org (OPEN_QUESTIONS Q7)
    actor_type   text NOT NULL CHECK (actor_type IN ('user','staff','system','api_key')),
    actor_id     text,
    action       text NOT NULL,
    target_type  text,
    target_id    text,
    ip           inet,
    ua           text,
    details      jsonb NOT NULL DEFAULT '{}'::jsonb,
    prev_hash    bytea NOT NULL CHECK (length(prev_hash) = 32),
    hash         bytea NOT NULL CHECK (length(hash) = 32)
);
CREATE INDEX audit_event_org_idx ON audit_event (org_id, id);
CREATE INDEX audit_event_action_idx ON audit_event (action);

CREATE FUNCTION audit_event_append_only() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'audit_event is append-only';
END $$;
CREATE TRIGGER audit_event_append_only BEFORE UPDATE OR DELETE ON audit_event
    FOR EACH ROW EXECUTE FUNCTION audit_event_append_only();
CREATE TRIGGER audit_event_no_truncate BEFORE TRUNCATE ON audit_event
    FOR EACH STATEMENT EXECUTE FUNCTION audit_event_append_only();

CREATE TABLE audit_verification_run (
    id             bigserial PRIMARY KEY,
    ran_at         timestamptz NOT NULL DEFAULT now(),
    chain          uuid NOT NULL,
    ok             boolean NOT NULL,
    checked        integer NOT NULL,
    last_event_id  bigint,
    last_hash      bytea,
    first_bad_id   bigint,
    reason         text
);
CREATE INDEX audit_verification_run_chain_idx ON audit_verification_run (chain, id DESC);

CREATE TABLE notification (
    id          uuid PRIMARY KEY,
    org_id      uuid NOT NULL REFERENCES org(id) ON DELETE CASCADE,
    user_id     uuid NOT NULL REFERENCES app_user(id) ON DELETE CASCADE,
    type        text NOT NULL,
    payload     jsonb NOT NULL DEFAULT '{}'::jsonb,
    read_at     timestamptz,
    created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX notification_user_idx ON notification (org_id, user_id, created_at DESC);

CREATE TABLE notification_preference (
    user_id     uuid NOT NULL REFERENCES app_user(id) ON DELETE CASCADE,
    org_id      uuid NOT NULL REFERENCES org(id) ON DELETE CASCADE,
    event_type  text NOT NULL,
    email       boolean NOT NULL DEFAULT true,
    in_app      boolean NOT NULL DEFAULT true,
    PRIMARY KEY (user_id, org_id, event_type)
);

CREATE TABLE feature_flag (
    key         text NOT NULL,
    scope       text NOT NULL CHECK (scope IN ('global','plan','org')),
    scope_id    text NOT NULL DEFAULT '',
    value       jsonb NOT NULL,
    updated_by  text,
    updated_at  timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (key, scope, scope_id)
);

CREATE TABLE idempotency_record (
    principal    text NOT NULL,
    route        text NOT NULL,
    key          text NOT NULL,
    status_code  integer NOT NULL,
    response     jsonb NOT NULL,
    created_at   timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (principal, route, key)
);
"""


def _rls(table: str, using: str) -> str:
    return (
        f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;\n"
        f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY;\n"
        f"CREATE POLICY {table}_scope ON {table} USING ({using}) WITH CHECK ({using});\n"
    )


RLS_SQL = "\n".join(
    [
        _rls(
            "org",
            f"{PLATFORM} OR id = {ORG} OR EXISTS (SELECT 1 FROM membership m WHERE m.org_id = org.id "
            f"AND m.user_id = {USER} AND m.status = 'active')",
        ),
        _rls("membership", f"{PLATFORM} OR org_id = {ORG} OR user_id = {USER}"),
        _rls("invite", f"{PLATFORM} OR org_id = {ORG}"),
        _rls("tenant_key", f"{PLATFORM} OR org_id = {ORG}"),
        _rls("tenant_db", f"{PLATFORM} OR org_id = {ORG}"),
        _rls("credential", f"{PLATFORM} OR org_id = {ORG}"),
        _rls("audit_event", f"{PLATFORM} OR (org_id IS NOT NULL AND org_id = {ORG})"),
        # Notifications: a user reads/updates only their own; inserts may target any *member* of the active org
        # (e.g. "member joined" sent to the inviter by the invitee's request).
        "ALTER TABLE notification ENABLE ROW LEVEL SECURITY;\nALTER TABLE notification FORCE ROW LEVEL SECURITY;\n"
        f"CREATE POLICY notification_read ON notification FOR SELECT USING ({PLATFORM} OR (org_id = {ORG} "
        f"AND user_id = {USER}));\n"
        f"CREATE POLICY notification_update ON notification FOR UPDATE USING ({PLATFORM} OR (org_id = {ORG} "
        f"AND user_id = {USER})) WITH CHECK ({PLATFORM} OR (org_id = {ORG} AND user_id = {USER}));\n"
        f"CREATE POLICY notification_delete ON notification FOR DELETE USING ({PLATFORM});\n"
        f"CREATE POLICY notification_insert ON notification FOR INSERT WITH CHECK ({PLATFORM} OR (org_id = {ORG} "
        f"AND EXISTS (SELECT 1 FROM membership m WHERE m.org_id = notification.org_id "
        f"AND m.user_id = notification.user_id)));\n",
        _rls("notification_preference", f"{PLATFORM} OR (org_id = {ORG} AND user_id = {USER})"),
        # data-api may read only the tenant read-only role password, never owner/rw or source secrets.
        "CREATE POLICY credential_reader_ro_only ON credential AS RESTRICTIVE FOR SELECT TO dcs_control_reader "
        "USING (kind = 'tenant_db_role:ro');",
    ]
)

GRANTS_SQL = """
REVOKE ALL ON ALL TABLES IN SCHEMA public FROM PUBLIC;
GRANT USAGE ON SCHEMA public TO dcs_control_app, dcs_control_reader;

GRANT SELECT, INSERT, UPDATE, DELETE ON
    org, app_user, membership, invite, tenant_key, tenant_db, credential,
    notification, notification_preference, feature_flag, idempotency_record
    TO dcs_control_app;
GRANT SELECT, INSERT ON audit_event, audit_verification_run TO dcs_control_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO dcs_control_app;

GRANT SELECT ON org, app_user, membership, tenant_db, tenant_key, credential, feature_flag TO dcs_control_reader;
"""


def upgrade() -> None:
    op.execute(TABLES_SQL)
    op.execute(RLS_SQL)
    op.execute(GRANTS_SQL)


def downgrade() -> None:
    op.execute(
        """
        DROP TABLE IF EXISTS idempotency_record, feature_flag, notification_preference, notification,
            audit_verification_run, credential, tenant_db, tenant_key, invite, membership, app_user, org CASCADE;
        DROP TABLE IF EXISTS audit_event CASCADE;
        DROP FUNCTION IF EXISTS audit_event_append_only();
        DROP FUNCTION IF EXISTS org_region_immutable();
        """
    )
