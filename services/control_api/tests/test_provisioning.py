"""Signup → provisioning → deprovisioning, audit chain and RLS against real Postgres + MinIO (SPEC §13 P0)."""

from __future__ import annotations

import time
import uuid
from typing import Any

import asyncpg
import pytest

from control_api.workflows.activities import credential_kind

pytestmark = pytest.mark.integration

TENANT_SCHEMAS = {
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
}


def admin_dsn(cluster: Any, db: str = "postgres") -> str:
    return cluster.admin_url.rsplit("/", 1)[0] + f"/{db}"


async def audit_actions(cluster: Any, org_id: str) -> list[str]:
    conn = await asyncpg.connect(admin_dsn(cluster, "dcs_control"))
    try:
        rows = await conn.fetch(
            "SELECT action FROM audit_event WHERE org_id = $1 ORDER BY id", uuid.UUID(org_id)
        )
        return [r["action"] for r in rows]
    finally:
        await conn.close()


async def test_signup_provisions_tenant_in_under_30s(control: Any, cluster: Any) -> None:
    started = time.monotonic()
    token, org = await control.signup("Northwind Fitness", "IN")
    elapsed = time.monotonic() - started
    assert elapsed < 30, f"provisioning took {elapsed:.1f}s"
    tenant_id = org["tenant_id"]
    assert org["region"] == "ap-south-1"

    detail = await control.client.get(f"/v1/orgs/{org['id']}", headers=control.auth(token, org["id"]))
    assert detail.status_code == 200
    assert detail.json()["status"] == "active"

    conn = await asyncpg.connect(admin_dsn(cluster))
    try:
        assert await conn.fetchval("SELECT 1 FROM pg_database WHERE datname = $1", tenant_id) == 1
        roles = {
            r["rolname"]: r["rolcanlogin"]
            for r in await conn.fetch(
                "SELECT rolname, rolcanlogin FROM pg_roles WHERE rolname LIKE $1", f"{tenant_id}\\_%"
            )
        }
        assert roles == {
            f"{tenant_id}_owner": True,
            f"{tenant_id}_rw": True,
            f"{tenant_id}_ro": True,
            f"{tenant_id}_engine_ro": False,
        }
        assert not await conn.fetchval("SELECT has_database_privilege('public', $1, 'CONNECT')", tenant_id)
    finally:
        await conn.close()

    tconn = await asyncpg.connect(admin_dsn(cluster, tenant_id))
    try:
        schemas = {r["nspname"] for r in await tconn.fetch("SELECT nspname FROM pg_namespace")}
        assert schemas >= TENANT_SCHEMAS
        exts = {r["extname"] for r in await tconn.fetch("SELECT extname FROM pg_extension")}
        assert {"pgcrypto", "pg_trgm", "vector"} <= exts
    finally:
        await tconn.close()

    async with control.state.db.platform_tx() as s:
        from control_api.models import Credential, TenantDb, TenantKey

        key = await s.get(TenantKey, uuid.UUID(org["id"]))
        db = await s.get(TenantDb, uuid.UUID(org["id"]))
        from sqlalchemy import select

        kinds = set(
            (await s.scalars(select(Credential.kind).where(Credential.org_id == uuid.UUID(org["id"])))).all()
        )
    assert key is not None and key.status == "active" and key.kms_key_arn.startswith("local:")
    assert db is not None and db.status == "ready" and db.cbm_version == "0.0"
    assert kinds == {credential_kind(k) for k in ("owner", "rw", "ro")}

    prefixes = await control.store.prefixes_present(tenant_id)
    assert prefixes == sorted(
        f"tenants/{tenant_id}/{z}/.dcs-prefix" for z in ("landing", "bronze", "exports", "browser-artifacts")
    )

    actions = await audit_actions(cluster, org["id"])
    assert actions == [
        "org.created",
        "tenant.provision.idp_group_created",
        "tenant.provision.key_created",
        "tenant.provision.database_created",
        "tenant.provision.migrated",
        "tenant.provision.prefixes_created",
        "tenant.provisioned",
    ]
    notes = await control.client.get("/v1/notifications", headers=control.auth(token, org["id"]))
    assert [n["type"] for n in notes.json()["items"]] == ["tenant.provisioned"]


async def test_tenant_role_grants(control: Any, cluster: Any) -> None:
    _, org = await control.signup("Grant Check Ltd", "GB")
    tenant_id = org["tenant_id"]
    acts = control.state.workflows.activities
    pw = {k: await acts.role_password(org["id"], tenant_id, k) for k in ("ro", "rw")}
    base = cluster.admin_url.split("@", 1)[1].rsplit("/", 1)[0]

    rw = await asyncpg.connect(f"postgresql://{tenant_id}_rw:{pw['rw']}@{base}/{tenant_id}")
    try:
        await rw.execute("INSERT INTO audit_local.event (actor_type, action) VALUES ('system', 'test.write')")
        with pytest.raises(asyncpg.PostgresError):
            await rw.execute("UPDATE audit_local.event SET action = 'x'")
        with pytest.raises(asyncpg.InsufficientPrivilegeError):
            await rw.execute("CREATE TABLE core.sneaky (id int)")
    finally:
        await rw.close()

    ro = await asyncpg.connect(f"postgresql://{tenant_id}_ro:{pw['ro']}@{base}/{tenant_id}")
    try:
        assert await ro.fetchval("SELECT count(*) FROM audit_local.event") >= 1
        with pytest.raises(asyncpg.InsufficientPrivilegeError):
            await ro.execute("INSERT INTO audit_local.event (actor_type, action) VALUES ('system', 'nope')")
    finally:
        await ro.close()

    with pytest.raises(asyncpg.PostgresError):  # engine_ro is a NOLOGIN template
        await asyncpg.connect(f"postgresql://{tenant_id}_engine_ro:x@{base}/{tenant_id}")


async def test_tenant_roles_cannot_cross_databases(control: Any, cluster: Any) -> None:
    _, a = await control.signup("Tenant A", "IN")
    _, b = await control.signup("Tenant B", "IN")
    acts = control.state.workflows.activities
    pw_a = await acts.role_password(a["id"], a["tenant_id"], "ro")
    base = cluster.admin_url.split("@", 1)[1].rsplit("/", 1)[0]
    with pytest.raises(asyncpg.InsufficientPrivilegeError):
        await asyncpg.connect(f"postgresql://{a['tenant_id']}_ro:{pw_a}@{base}/{b['tenant_id']}")


async def test_deprovision_removes_everything_and_audits_each_step(control: Any, cluster: Any) -> None:
    owner, org = await control.signup("Short Lived Co", "IN")
    tenant_id = org["tenant_id"]
    staff = control.tokens.staff("staff-admin-1", ["staff_admin"])

    bad = await control.client.post(
        f"/v1/admin/tenants/{org['id']}/deprovision",
        json={"confirm_slug": "wrong", "reason": "test cleanup", "pending_days": 7},
        headers=control.auth(staff),
    )
    assert bad.status_code == 422

    resp = await control.client.post(
        f"/v1/admin/tenants/{org['id']}/deprovision",
        json={"confirm_slug": org["slug"], "reason": "test cleanup", "pending_days": 7},
        headers=control.auth(staff),
    )
    assert resp.status_code == 202, resp.text
    assert resp.json()["workflow_id"] == f"wf:deprovision:{tenant_id}:v1"

    conn = await asyncpg.connect(admin_dsn(cluster))
    try:
        assert await conn.fetchval("SELECT 1 FROM pg_database WHERE datname = $1", tenant_id) is None
        assert (
            await conn.fetchval("SELECT count(*) FROM pg_roles WHERE rolname LIKE $1", f"{tenant_id}\\_%")
            == 0
        )
    finally:
        await conn.close()
    assert await control.store.prefixes_present(tenant_id) == []

    async with control.state.db.platform_tx() as s:
        from control_api.models import Org, TenantKey

        key = await s.get(TenantKey, uuid.UUID(org["id"]))
        o = await s.get(Org, uuid.UUID(org["id"]))
    assert key is not None and key.status == "pending_deletion" and key.deletion_scheduled_at is not None
    assert o is not None and o.status == "deleted"
    state = await control.state.vault.key_service.describe(key.kms_key_arn)
    assert state.status == "pending_deletion"

    actions = await audit_actions(cluster, org["id"])
    assert actions[-6:] == [
        "tenant.deprovision.requested",
        "tenant.deprovision.idp_group_deleted",
        "tenant.deprovision.database_dropped",
        "tenant.deprovision.prefixes_deleted",
        "tenant.deprovision.key_deletion_scheduled",
        "tenant.deprovisioned",
    ]
    # The former owner can no longer reach the org.
    gone = await control.client.get(f"/v1/orgs/{org['id']}", headers=control.auth(owner, org["id"]))
    assert gone.status_code == 404


async def test_audit_chain_verification_detects_tampering(control: Any, cluster: Any) -> None:
    _, org = await control.signup("Audit Probe", "IN")
    staff = control.tokens.staff("staff-ops-1", ["staff_ops"])
    run = await control.client.post("/v1/admin/audit/verify", headers=control.auth(staff))
    assert run.status_code == 202
    status = (await control.client.get("/v1/admin/audit/verification", headers=control.auth(staff))).json()
    by_chain = {s["chain"]: s for s in status}
    assert by_chain[org["id"]]["ok"] is True
    assert all(s["ok"] for s in status)

    conn = await asyncpg.connect(admin_dsn(cluster, "dcs_control"))
    try:
        target = await conn.fetchval(
            "SELECT min(id) FROM audit_event WHERE org_id = $1", uuid.UUID(org["id"])
        )
        await conn.execute("ALTER TABLE audit_event DISABLE TRIGGER audit_event_append_only")
        await conn.execute("UPDATE audit_event SET details = '{\"forged\": true}' WHERE id = $1", target)
        await conn.execute("ALTER TABLE audit_event ENABLE TRIGGER audit_event_append_only")
    finally:
        await conn.close()

    await control.client.post("/v1/admin/audit/verify", headers=control.auth(staff))
    status = (await control.client.get("/v1/admin/audit/verification", headers=control.auth(staff))).json()
    bad = {s["chain"]: s for s in status}[org["id"]]
    assert bad["ok"] is False
    assert bad["first_bad_id"] == target
    dash = (await control.client.get("/v1/admin/dashboard", headers=control.auth(staff))).json()
    assert dash["audit_chains_failing"] >= 1


async def test_audit_log_is_append_only_for_the_app_role(control: Any, cluster: Any) -> None:
    conn = await asyncpg.connect(
        cluster.control("dcs_control_app").replace("postgresql+asyncpg", "postgresql")
    )
    try:
        await conn.execute("SELECT set_config('app.scope', 'platform', false)")
        with pytest.raises(asyncpg.PostgresError):
            await conn.execute("UPDATE audit_event SET action = 'x'")
        with pytest.raises(asyncpg.PostgresError):
            await conn.execute("DELETE FROM audit_event")
    finally:
        await conn.close()


async def test_rls_hides_other_orgs_from_the_app_role(control: Any, cluster: Any) -> None:
    _, a = await control.signup("RLS A", "IN")
    _, b = await control.signup("RLS B", "IN")
    conn = await asyncpg.connect(
        cluster.control("dcs_control_app").replace("postgresql+asyncpg", "postgresql")
    )
    try:
        async with conn.transaction():
            await conn.execute("SELECT set_config('app.org_id', $1, true)", a["id"])
            for table in ("org", "tenant_db", "tenant_key", "credential", "invite"):
                col = "id" if table == "org" else "org_id"
                ids = {r[0] for r in await conn.fetch(f"SELECT {col} FROM {table}")}
                assert uuid.UUID(b["id"]) not in ids, table
            assert (
                await conn.fetchval("SELECT count(*) FROM audit_event WHERE org_id = $1", uuid.UUID(b["id"]))
                == 0
            )
            assert (
                await conn.fetchval("SELECT count(*) FROM audit_event WHERE org_id = $1", uuid.UUID(a["id"]))
                > 0
            )
        async with conn.transaction():  # no scope at all → nothing
            assert await conn.fetchval("SELECT count(*) FROM org") == 0
            assert await conn.fetchval("SELECT count(*) FROM credential") == 0
        async with conn.transaction():  # cannot write into another org
            await conn.execute("SELECT set_config('app.org_id', $1, true)", a["id"])
            with pytest.raises(asyncpg.PostgresError):
                await conn.execute(
                    "INSERT INTO notification (id, org_id, user_id, type) SELECT gen_random_uuid(), $1, id, 'x' "
                    "FROM app_user LIMIT 1",
                    uuid.UUID(b["id"]),
                )
    finally:
        await conn.close()


async def test_reader_role_sees_only_ro_credentials(control: Any, cluster: Any) -> None:
    _, org = await control.signup("Reader Check", "IN")
    conn = await asyncpg.connect(
        cluster.control("dcs_control_reader").replace("postgresql+asyncpg", "postgresql")
    )
    try:
        async with conn.transaction():
            await conn.execute("SELECT set_config('app.org_id', $1, true)", org["id"])
            kinds = {r[0] for r in await conn.fetch("SELECT kind FROM credential")}
            assert kinds == {"tenant_db_role:ro"}
            with pytest.raises(asyncpg.InsufficientPrivilegeError):
                await conn.execute("DELETE FROM credential")
    finally:
        await conn.close()


async def test_region_and_tenant_id_are_immutable(control: Any, cluster: Any) -> None:
    _, org = await control.signup("Residency Ltd", "DE")
    assert org["region"] == "eu-west-2"
    conn = await asyncpg.connect(admin_dsn(cluster, "dcs_control"))
    try:
        with pytest.raises(asyncpg.RaiseError, match="immutable"):
            await conn.execute("UPDATE org SET region = 'ap-south-1' WHERE id = $1", uuid.UUID(org["id"]))
    finally:
        await conn.close()


async def test_provisioning_failure_marks_org_failed_and_retry_succeeds(control: Any, cluster: Any) -> None:
    acts = control.state.workflows.activities
    original = acts.store

    class Broken:
        async def create_prefixes(self, *_: Any) -> list[str]:
            raise RuntimeError("object store unavailable")

    acts.store = Broken()
    try:
        email_token, _ = await control.user(mfa=True)
        # The org row is committed before provisioning starts; the failure is recorded, not raised to the user.
        created = await control.client.post(
            "/v1/orgs", json={"name": "Flaky", "country": "IN"}, headers=control.auth(email_token)
        )
        assert created.status_code == 201
    finally:
        acts.store = original

    me = (await control.client.get("/v1/me", headers=control.auth(email_token))).json()
    org = next(m for m in me["memberships"] if m["org_name"] == "Flaky")
    assert org["org_status"] == "failed"

    staff = control.tokens.staff("staff-ops-2", ["staff_ops"])
    retry = await control.client.post(
        f"/v1/admin/tenants/{org['org_id']}/retry-provisioning", headers=control.auth(staff)
    )
    assert retry.status_code == 202, retry.text
    me = (await control.client.get("/v1/me", headers=control.auth(email_token))).json()
    assert next(m for m in me["memberships"] if m["org_name"] == "Flaky")["org_status"] == "active"
    actions = await audit_actions(cluster, org["org_id"])
    assert "tenant.provision.failed" in actions
    assert actions[-1] == "tenant.provisioned"
