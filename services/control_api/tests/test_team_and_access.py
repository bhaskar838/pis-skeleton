"""Invites, role changes, MFA enforcement, org context and the remaining customer routes (SPEC §8.3, §8.4)."""

from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import asyncpg
import pytest

pytestmark = pytest.mark.integration


def invite_token(control: Any, email: str) -> str:
    mail = next(m for m in reversed(control.state.mailer.sent) if m.to == email)
    match = re.search(r"/auth/invite/([A-Za-z0-9_-]+)", mail.text)
    assert match, mail.text
    return match.group(1)


async def invite(control: Any, owner: str, org_id: str, email: str, role: str) -> str:
    r = await control.client.post(
        f"/v1/orgs/{org_id}/invites", json={"email": email, "role": role}, headers=control.auth(owner, org_id)
    )
    assert r.status_code == 201, r.text
    return invite_token(control, email)


async def test_invite_accept_and_limited_role(control: Any) -> None:
    owner, org = await control.signup("Invite Co", "IN")
    analyst, email = await control.user()
    token = await invite(control, owner, org["id"], email, "analyst")

    preview = await control.client.get(f"/v1/invites/{token}")
    assert preview.status_code == 200
    body = preview.json()
    assert body["org_name"] == "Invite Co" and body["role"] == "analyst" and body["status"] == "pending"
    assert email not in body["email_hint"]

    accepted = await control.client.post(f"/v1/invites/{token}/accept", headers=control.auth(analyst))
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["role"] == "analyst"
    assert "members:read" not in accepted.json()["permissions"]

    # single use
    again = await control.client.post(f"/v1/invites/{token}/accept", headers=control.auth(analyst))
    assert again.status_code == 404

    me = (await control.client.get("/v1/me", headers=control.auth(analyst))).json()
    m = next(x for x in me["memberships"] if x["org_id"] == org["id"])
    assert m["role"] == "analyst" and "tools:run" in m["permissions"]

    forbidden = await control.client.get(
        f"/v1/orgs/{org['id']}/members", headers=control.auth(analyst, org["id"])
    )
    assert forbidden.status_code == 403
    assert forbidden.json()["permission"] == "members:read"
    ok = await control.client.get(f"/v1/orgs/{org['id']}", headers=control.auth(analyst, org["id"]))
    assert ok.status_code == 200

    team = (
        await control.client.get(f"/v1/orgs/{org['id']}/members", headers=control.auth(owner, org["id"]))
    ).json()
    assert {x["role"] for x in team["members"]} == {"owner", "analyst"}

    owner_notes = (
        await control.client.get("/v1/notifications", headers=control.auth(owner, org["id"]))
    ).json()
    assert "member.joined" in {n["type"] for n in owner_notes["items"]}


async def test_role_change_takes_effect_immediately_and_mfa_is_enforced(control: Any) -> None:
    owner, org = await control.signup("Role Change Co", "IN")
    member, email = await control.user(mfa=False)
    token = await invite(control, owner, org["id"], email, "viewer")
    m = (await control.client.post(f"/v1/invites/{token}/accept", headers=control.auth(member))).json()

    r = await control.client.get(f"/v1/orgs/{org['id']}/members", headers=control.auth(member, org["id"]))
    assert r.status_code == 403

    change = await control.client.patch(
        f"/v1/memberships/{m['membership_id']}",
        json={"role": "admin"},
        headers=control.auth(owner, org["id"]),
    )
    assert change.status_code == 200, change.text

    # Admin requires MFA: the same (non-MFA) token is now refused with a step-up hint.
    r = await control.client.get(f"/v1/orgs/{org['id']}/members", headers=control.auth(member, org["id"]))
    assert r.status_code == 403
    assert r.json()["type"].endswith("/mfa-required")

    sub = f"sub-{email}"
    with_mfa = control.tokens.customer(sub, email, mfa=True)
    r = await control.client.get(f"/v1/orgs/{org['id']}/members", headers=control.auth(with_mfa, org["id"]))
    assert r.status_code == 200

    notes = (await control.client.get("/v1/notifications", headers=control.auth(with_mfa, org["id"]))).json()
    assert notes["items"][0]["type"] == "member.role_changed"


async def test_assignment_rules(control: Any) -> None:
    owner, org = await control.signup("Rules Co", "IN")
    admin, admin_email = await control.user(mfa=True)
    token = await invite(control, owner, org["id"], admin_email, "admin")
    await control.client.post(f"/v1/invites/{token}/accept", headers=control.auth(admin))
    headers_admin = control.auth(admin, org["id"])

    # Admin cannot invite an owner
    r = await control.client.post(
        f"/v1/orgs/{org['id']}/invites",
        json={"email": "x@example.test", "role": "owner"},
        headers=headers_admin,
    )
    assert r.status_code == 403

    team = (await control.client.get(f"/v1/orgs/{org['id']}/members", headers=headers_admin)).json()
    owner_m = next(x for x in team["members"] if x["role"] == "owner")
    admin_m = next(x for x in team["members"] if x["role"] == "admin")

    # Admin cannot change or remove an owner
    r = await control.client.patch(
        f"/v1/memberships/{owner_m['id']}", json={"role": "viewer"}, headers=headers_admin
    )
    assert r.status_code == 403
    r = await control.client.delete(f"/v1/memberships/{owner_m['id']}", headers=headers_admin)
    assert r.status_code == 403
    # Nobody changes their own membership
    r = await control.client.patch(
        f"/v1/memberships/{admin_m['id']}", json={"role": "owner"}, headers=headers_admin
    )
    assert r.status_code == 403
    r = await control.client.patch(
        f"/v1/memberships/{owner_m['id']}", json={"role": "admin"}, headers=control.auth(owner, org["id"])
    )
    assert r.status_code == 403

    # Promote admin to owner, then the new owner can demote the original owner (two owners exist)
    r = await control.client.patch(
        f"/v1/memberships/{admin_m['id']}", json={"role": "owner"}, headers=control.auth(owner, org["id"])
    )
    assert r.status_code == 200
    r = await control.client.patch(
        f"/v1/memberships/{owner_m['id']}", json={"role": "viewer"}, headers=headers_admin
    )
    assert r.status_code == 200
    # ...but the last owner can never be demoted or removed (there is no other owner left to do it either)
    team = (await control.client.get(f"/v1/orgs/{org['id']}/members", headers=headers_admin)).json()
    assert [x["role"] for x in team["members"]].count("owner") == 1

    # Remove the demoted member
    r = await control.client.delete(f"/v1/memberships/{owner_m['id']}", headers=headers_admin)
    assert r.status_code == 204
    gone = await control.client.get(f"/v1/orgs/{org['id']}", headers=control.auth(owner, org["id"]))
    assert gone.status_code == 404


async def test_invite_email_mismatch_expiry_and_revoke(control: Any, cluster: Any) -> None:
    owner, org = await control.signup("Invite Guard Co", "IN")
    _, email = await control.user()
    token = await invite(control, owner, org["id"], email, "viewer")
    stranger, _ = await control.user()
    r = await control.client.post(f"/v1/invites/{token}/accept", headers=control.auth(stranger))
    assert r.status_code == 403

    unverified = control.tokens.customer(f"sub-{email}", email, verified=False)
    r = await control.client.post(f"/v1/invites/{token}/accept", headers=control.auth(unverified))
    assert r.status_code == 403
    assert r.json()["type"].endswith("/email-unverified")

    conn = await asyncpg.connect(cluster.admin_url.rsplit("/", 1)[0] + "/dcs_control")
    try:
        await conn.execute(
            "UPDATE invite SET expires_at = $1 WHERE org_id = $2 AND status = 'pending'",
            datetime.now(UTC) - timedelta(minutes=1),
            uuid.UUID(org["id"]),
        )
        actions = [
            r["action"]
            for r in await conn.fetch(
                "SELECT action FROM audit_event WHERE org_id = $1", uuid.UUID(org["id"])
            )
        ]
    finally:
        await conn.close()
    assert "member.invite_email_mismatch" in actions
    assert (await control.client.get(f"/v1/invites/{token}")).json()["status"] == "expired"
    member = control.tokens.customer(f"sub-{email}", email)
    r = await control.client.post(f"/v1/invites/{token}/accept", headers=control.auth(member))
    assert r.status_code == 410

    # Re-invite, then revoke
    token2 = await invite(control, owner, org["id"], email, "viewer")
    team = (
        await control.client.get(f"/v1/orgs/{org['id']}/members", headers=control.auth(owner, org["id"]))
    ).json()
    inv = next(i for i in team["invites"] if i["email"] == email)
    r = await control.client.delete(
        f"/v1/orgs/{org['id']}/invites/{inv['id']}", headers=control.auth(owner, org["id"])
    )
    assert r.status_code == 204
    assert (await control.client.get(f"/v1/invites/{token2}")).status_code == 404
    assert (await control.client.get("/v1/invites/short")).status_code == 404


async def test_org_context_and_token_rules(control: Any) -> None:
    owner, org = await control.signup("Context Co", "IN")
    other, _ = await control.user()

    assert (await control.client.get("/v1/me")).status_code == 401
    assert (await control.client.get("/v1/me", headers={"Authorization": "Bearer junk"})).status_code == 401
    r = await control.client.get(f"/v1/orgs/{org['id']}", headers=control.auth(owner))
    assert r.status_code == 400 and r.json()["type"].endswith("/org-required")
    assert (
        await control.client.get(f"/v1/orgs/{org['id']}", headers=control.auth(owner, "nope"))
    ).status_code == 404
    # Not a member → 404 (not 403), so org IDs cannot be probed
    assert (
        await control.client.get(f"/v1/orgs/{org['id']}", headers=control.auth(other, org["id"]))
    ).status_code == 404
    # Path org must equal the header org
    _, org2 = await control.signup("Context Co 2", "IN")
    r = await control.client.get(f"/v1/orgs/{org2['id']}", headers=control.auth(owner, org["id"]))
    assert r.status_code == 404

    staff = control.tokens.staff("staff-1", ["staff_admin"])
    assert (await control.client.get("/v1/me", headers=control.auth(staff))).status_code == 403
    assert (await control.client.get("/v1/admin/tenants", headers=control.auth(owner))).status_code == 403
    no_role = control.tokens.staff("staff-2", ["offline_access"])
    assert (await control.client.get("/v1/admin/tenants", headers=control.auth(no_role))).status_code == 403
    no_mfa = control.tokens.staff("staff-3", ["staff_admin"], mfa=False)
    r = await control.client.get("/v1/admin/tenants", headers=control.auth(no_mfa))
    assert r.json()["type"].endswith("/mfa-required")
    support = control.tokens.staff("staff-4", ["staff_support"])
    r = await control.client.post(
        f"/v1/admin/tenants/{org['id']}/deprovision",
        json={"confirm_slug": org["slug"], "reason": "nope"},
        headers=control.auth(support),
    )
    assert r.status_code == 403


async def test_owner_without_mfa_is_stepped_up(control: Any) -> None:
    _, email = await control.user()
    no_mfa = control.tokens.customer(f"sub-{email}", email, mfa=False)
    created = await control.client.post(
        "/v1/orgs", json={"name": "MFA Co", "country": "IN"}, headers=control.auth(no_mfa)
    )
    assert created.status_code == 201  # creating an org is allowed; using it as owner needs MFA
    org_id = created.json()["id"]
    r = await control.client.get(f"/v1/orgs/{org_id}", headers=control.auth(no_mfa, org_id))
    assert r.status_code == 403 and r.json()["step_up_acr"] == "mfa"


async def test_signup_rules_and_idempotency(control: Any) -> None:
    _, email = await control.user()
    unverified = control.tokens.customer(f"sub-{email}", email, verified=False, mfa=True)
    r = await control.client.post(
        "/v1/orgs", json={"name": "X", "country": "IN"}, headers=control.auth(unverified)
    )
    assert r.status_code == 403

    token = control.tokens.customer(f"sub-{email}", email, mfa=True)
    bad = await control.client.post(
        "/v1/orgs", json={"name": "X", "country": "I1"}, headers=control.auth(token)
    )
    assert bad.status_code == 422
    extra = await control.client.post(
        "/v1/orgs", json={"name": "X", "country": "IN", "region": "eu-west-2"}, headers=control.auth(token)
    )
    assert extra.status_code == 422

    headers = {**control.auth(token), "Idempotency-Key": "signup-key-0001"}
    first = await control.client.post("/v1/orgs", json={"name": "Idem Co", "country": "IN"}, headers=headers)
    second = await control.client.post("/v1/orgs", json={"name": "Idem Co", "country": "IN"}, headers=headers)
    assert first.status_code == second.status_code == 201
    assert first.json()["id"] == second.json()["id"]
    bad_key = await control.client.post(
        "/v1/orgs",
        json={"name": "Y", "country": "IN"},
        headers={**control.auth(token), "Idempotency-Key": "x"},
    )
    assert bad_key.status_code == 400

    for i in range(2):
        r = await control.client.post(
            "/v1/orgs", json={"name": f"Limit {i}", "country": "IN"}, headers=control.auth(token)
        )
        assert r.status_code == 201
    limit = await control.client.post(
        "/v1/orgs", json={"name": "Limit 3", "country": "IN"}, headers=control.auth(token)
    )
    assert limit.status_code == 409 and limit.json()["type"].endswith("/org-limit")


async def test_profile_audit_notifications_flags_security(control: Any) -> None:
    owner, org = await control.signup("Profile Co", "IN")
    h = control.auth(owner, org["id"])

    r = await control.client.patch(
        f"/v1/orgs/{org['id']}/profile",
        json={
            "name": "Profile Co Ltd",
            "business_profile": {
                "industry": "fitness",
                "currency": "INR",
                "timezone": "Asia/Kolkata",
                "customer_type": "B2C",
                "fiscal_year_start": "04-01",
            },
        },
        headers=h,
    )
    assert r.status_code == 200, r.text
    assert r.json()["profile_version"] == 2 and r.json()["name"] == "Profile Co Ltd"
    bad = await control.client.patch(
        f"/v1/orgs/{org['id']}/profile", json={"business_profile": {"timezone": "Mars/Base"}}, headers=h
    )
    assert bad.status_code == 422
    region = await control.client.patch(
        f"/v1/orgs/{org['id']}/profile", json={"region": "eu-west-2"}, headers=h
    )
    assert region.status_code == 422

    audit = (await control.client.get("/v1/audit", params={"limit": 3}, headers=h)).json()
    assert audit["items"][0]["action"] == "org.profile.updated"
    assert audit["items"][0]["details"]["fields"]
    assert audit["next_cursor"] is not None
    page2 = (
        await control.client.get("/v1/audit", params={"limit": 3, "cursor": audit["next_cursor"]}, headers=h)
    ).json()
    assert page2["items"][0]["id"] < audit["items"][-1]["id"] + 1
    filtered = (
        await control.client.get("/v1/audit", params={"action": "tenant.provision"}, headers=h)
    ).json()
    assert all(i["action"].startswith("tenant.provision") for i in filtered["items"])
    assert (await control.client.get("/v1/audit", params={"cursor": "abc"}, headers=h)).status_code == 400

    notes = (await control.client.get("/v1/notifications", params={"unread_only": True}, headers=h)).json()
    nid = notes["items"][0]["id"]
    assert (await control.client.post(f"/v1/notifications/{nid}/read", headers=h)).status_code == 204
    assert (await control.client.post(f"/v1/notifications/{uuid.uuid4()}/read", headers=h)).status_code == 404
    assert (await control.client.post("/v1/notifications/read-all", headers=h)).status_code == 204
    assert (await control.client.get("/v1/notifications", params={"unread_only": True}, headers=h)).json()[
        "items"
    ] == []

    prefs = (await control.client.get("/v1/notification-preferences", headers=h)).json()
    assert {p["event_type"] for p in prefs["items"]} >= {"tenant.provisioned", "member.joined"}
    upd = await control.client.put(
        "/v1/notification-preferences",
        json={"items": [{"event_type": "member.joined", "email": False, "in_app": True}]},
        headers=h,
    )
    assert next(p for p in upd.json()["items"] if p["event_type"] == "member.joined")["email"] is False
    bad = await control.client.put(
        "/v1/notification-preferences",
        json={"items": [{"event_type": "nope", "email": False, "in_app": True}]},
        headers=h,
    )
    assert bad.status_code == 422

    sec = (await control.client.get("/v1/security/summary", headers=h)).json()
    assert sec["your_role_requires_mfa"] is True and sec["session_mfa"] is True
    assert set(sec["mfa_required_roles"]) == {"owner", "admin"}

    staff = control.tokens.staff("staff-flags", ["staff_ops"])
    flags = (await control.client.get("/v1/flags", headers=h)).json()["flags"]
    assert flags["system.maintenance"] is False
    put = await control.client.put(
        "/v1/admin/flags",
        json={"key": "ui.insights_feed", "scope": "org", "scope_id": org["id"], "value": True},
        headers=control.auth(staff),
    )
    assert put.status_code == 200
    assert (await control.client.get("/v1/flags", headers=h)).json()["flags"]["ui.insights_feed"] is True
    bad_scope = await control.client.put(
        "/v1/admin/flags",
        json={"key": "x.y", "scope": "global", "scope_id": "z", "value": 1},
        headers=control.auth(staff),
    )
    assert bad_scope.status_code == 422
    listed = (await control.client.get("/v1/admin/flags", headers=control.auth(staff))).json()
    assert any(f["key"] == "ui.insights_feed" for f in listed)
    d = await control.client.delete(
        "/v1/admin/flags/ui.insights_feed",
        params={"scope": "org", "scope_id": org["id"]},
        headers=control.auth(staff),
    )
    assert d.status_code == 204
    assert (
        await control.client.delete(
            "/v1/admin/flags/ui.insights_feed",
            params={"scope": "org", "scope_id": org["id"]},
            headers=control.auth(staff),
        )
    ).status_code == 404
    # staff flag change is visible in the tenant's own audit log (G-04)
    actors = {i["actor_type"] for i in (await control.client.get("/v1/audit", headers=h)).json()["items"]}
    assert "staff" in actors


async def test_admin_tenant_views(control: Any) -> None:
    owner, org = await control.signup("Admin View Co", "IN")
    staff = control.tokens.staff("staff-view", ["staff_support"])
    hs = control.auth(staff)
    lst = (await control.client.get("/v1/admin/tenants", params={"q": "Admin View"}, headers=hs)).json()
    assert any(t["org_id"] == org["id"] and t["db_status"] == "ready" for t in lst["items"])
    detail = (await control.client.get(f"/v1/admin/tenants/{org['id']}", headers=hs)).json()
    assert detail["db"]["db_name"] == org["tenant_id"]
    assert detail["key"]["provider"] == "local" and "wrapped_dek" not in detail["key"]
    assert detail["member_count"] == 1 and len(detail["owners"]) == 1
    assert (await control.client.get(f"/v1/admin/tenants/{uuid.uuid4()}", headers=hs)).status_code == 404
    me = (await control.client.get("/v1/admin/me", headers=hs)).json()
    assert me["roles"] == ["staff_support"] and "platform:tenants:read" in me["permissions"]
    assert "platform:tenants:deprovision" not in me["permissions"] and me["session_mfa"] is True
    dash = (await control.client.get("/v1/admin/dashboard", headers=hs)).json()
    assert dash["tenants_by_status"].get("active", 0) >= 1
    audit = (
        await control.client.get(
            "/v1/admin/audit",
            params={"org_id": org["id"]},
            headers=control.auth(control.tokens.staff("s5", ["staff_ops"])),
        )
    ).json()
    assert audit["items"][0]["action"] == "staff.tenant.viewed"
    filt = await control.client.get(
        "/v1/admin/tenants", params={"status": "active", "region": "ap-south-1", "limit": 1}, headers=hs
    )
    assert filt.status_code == 200 and len(filt.json()["items"]) == 1
    conflict = await control.client.post(
        f"/v1/admin/tenants/{org['id']}/retry-provisioning",
        headers=control.auth(control.tokens.staff("s6", ["staff_ops"])),
    )
    assert conflict.status_code == 409
    # tenant sees the staff view in its own audit log
    own = (
        await control.client.get(
            "/v1/audit", params={"actor_type": "staff"}, headers=control.auth(owner, org["id"])
        )
    ).json()
    assert own["items"][0]["action"] == "staff.tenant.viewed"
