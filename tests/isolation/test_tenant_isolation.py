"""Tenant isolation test generator (SPEC §14.6) — blocking in CI.

1. Introspect the OpenAPI specs of control-api and data-api.
2. Every route must be classified in ROUTES; an unclassified (new) route fails the build.
3. For every tenant-scoped route: create tenants A and B, seed objects in B, then call the route as A using B's
   IDs in the path and B's org in the header. Expect 403/404 — never data. Afterwards B's objects are unchanged.
"""

from __future__ import annotations

import re
import uuid
from typing import Any

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.isolation]

# Isolation class per route: tenant | user | public | staff | health
CONTROL_ROUTES: dict[str, str] = {
    "GET /v1/me": "user",
    "POST /v1/orgs": "user",
    "GET /v1/orgs/{org_id}": "tenant",
    "PATCH /v1/orgs/{org_id}/profile": "tenant",
    "GET /v1/orgs/{org_id}/members": "tenant",
    "POST /v1/orgs/{org_id}/invites": "tenant",
    "DELETE /v1/orgs/{org_id}/invites/{invite_id}": "tenant",
    "PATCH /v1/memberships/{membership_id}": "tenant",
    "DELETE /v1/memberships/{membership_id}": "tenant",
    "GET /v1/invites/{token}": "public",
    "POST /v1/invites/{token}/accept": "user",
    "GET /v1/audit": "tenant",
    "GET /v1/notifications": "tenant",
    "POST /v1/notifications/{notification_id}/read": "tenant",
    "POST /v1/notifications/read-all": "tenant",
    "GET /v1/notification-preferences": "tenant",
    "PUT /v1/notification-preferences": "tenant",
    "GET /v1/flags": "tenant",
    "GET /v1/security/summary": "tenant",
    "GET /v1/admin/me": "staff",
    "GET /v1/admin/dashboard": "staff",
    "GET /v1/admin/tenants": "staff",
    "GET /v1/admin/tenants/{org_id}": "staff",
    "POST /v1/admin/tenants/{org_id}/deprovision": "staff",
    "POST /v1/admin/tenants/{org_id}/retry-provisioning": "staff",
    "GET /v1/admin/audit": "staff",
    "GET /v1/admin/audit/verification": "staff",
    "POST /v1/admin/audit/verify": "staff",
    "GET /v1/admin/flags": "staff",
    "PUT /v1/admin/flags": "staff",
    "DELETE /v1/admin/flags/{key}": "staff",
    # control panel (Phase 0.5)
    "GET /v1/admin/config": "staff",
    "PUT /v1/admin/config/{key}": "staff",
    "DELETE /v1/admin/config/{key}": "staff",
    "GET /v1/admin/config/{key}/history": "staff",
    "POST /v1/admin/config/{key}/revert/{version}": "staff",
    "PUT /v1/admin/secrets/{key}": "staff",
    "DELETE /v1/admin/secrets/{key}": "staff",
    "GET /v1/admin/regions": "staff",
    "POST /v1/admin/regions": "staff",
    "PATCH /v1/admin/regions/{code}": "staff",
    "GET /v1/admin/countries": "staff",
    "PATCH /v1/admin/countries/{code}": "staff",
    "GET /v1/public/brand": "public",
    "GET /v1/public/countries": "public",
}

DATA_ROUTES: dict[str, str] = {"GET /v1/tenant": "tenant"}

BODIES: dict[str, Any] = {
    "PATCH /v1/orgs/{org_id}/profile": {"name": "pwned"},
    "POST /v1/orgs/{org_id}/invites": {"email": "intruder@example.test", "role": "viewer"},
    "PATCH /v1/memberships/{membership_id}": {"role": "viewer"},
    "PUT /v1/notification-preferences": {
        "items": [{"event_type": "member.joined", "email": False, "in_app": False}]
    },
    "POST /v1/admin/tenants/{org_id}/deprovision": {"confirm_slug": "x", "reason": "attack"},
    "PUT /v1/admin/flags": {"key": "system.maintenance", "scope": "global", "value": True},
    "PUT /v1/admin/config/{key}": {"value": "pwned"},
    "PUT /v1/admin/secrets/{key}": {"value": "pwned"},
    "POST /v1/admin/regions": {"code": "xx-evil-1", "name": "Evil"},
    "PATCH /v1/admin/regions/{code}": {"status": "disabled"},
    "PATCH /v1/admin/countries/{code}": {"signup_enabled": True},
}


def routes_from_openapi(spec: dict[str, Any]) -> set[str]:
    out = set()
    for path, ops in spec["paths"].items():
        for method in ops:
            if method in ("get", "post", "put", "patch", "delete"):
                out.add(f"{method.upper()} {path}")
    return out


def fill(path: str, ids: dict[str, str]) -> str:
    return re.sub(r"\{(\w+)\}", lambda m: ids.get(m.group(1), str(uuid.uuid4())), path)


async def call(client: Any, route: str, ids: dict[str, str], headers: dict[str, str]) -> Any:
    method, path = route.split(" ", 1)
    return await client.request(method, fill(path, ids), json=BODIES.get(route), headers=headers)


@pytest.fixture(scope="module")
async def tenants(control: Any) -> dict[str, Any]:
    """Tenant A (attacker) and tenant B (victim) with objects seeded in B."""
    owner_a, org_a = await control.signup("Tenant A Attacker", "IN")
    owner_b, org_b = await control.signup("Tenant B Victim", "IN")
    hb = control.auth(owner_b, org_b["id"])
    member_b, member_email = await control.user()
    inv = await control.client.post(
        f"/v1/orgs/{org_b['id']}/invites", json={"email": member_email, "role": "viewer"}, headers=hb
    )
    token = re.search(r"/auth/invite/([\w-]+)", control.state.mailer.sent[-1].text).group(1)  # type: ignore[union-attr]
    await control.client.post(f"/v1/invites/{token}/accept", headers=control.auth(member_b))
    pending = await control.client.post(
        f"/v1/orgs/{org_b['id']}/invites",
        json={"email": "pending@example.test", "role": "analyst"},
        headers=hb,
    )
    team = (await control.client.get(f"/v1/orgs/{org_b['id']}/members", headers=hb)).json()
    membership_b = next(m for m in team["members"] if m["role"] == "viewer")
    notes = (await control.client.get("/v1/notifications", headers=hb)).json()
    assert inv.status_code == pending.status_code == 201
    return {
        "a": {"token": owner_a, "org": org_a},
        "b": {
            "token": owner_b,
            "org": org_b,
            "invite": pending.json(),
            "membership": membership_b,
            "notification": notes["items"][0],
        },
    }


def b_ids(t: dict[str, Any]) -> dict[str, str]:
    b = t["b"]
    return {
        "org_id": b["org"]["id"],
        "invite_id": b["invite"]["id"],
        "membership_id": b["membership"]["id"],
        "notification_id": b["notification"]["id"],
        "token": "x" * 43,
        "key": "system.maintenance",
    }


async def test_every_control_route_is_classified(control: Any) -> None:
    actual = routes_from_openapi(control.app.openapi())
    assert actual - set(CONTROL_ROUTES) == set(), "new routes must declare their isolation behaviour"
    assert set(CONTROL_ROUTES) - actual == set(), "classified routes that no longer exist"


async def test_every_data_route_is_classified(data: Any) -> None:
    actual = routes_from_openapi(data.app.openapi())
    assert actual == set(DATA_ROUTES)


@pytest.mark.parametrize("route", sorted(r for r, c in CONTROL_ROUTES.items() if c == "tenant"))
async def test_tenant_route_with_b_ids_under_a_org(control: Any, tenants: dict[str, Any], route: str) -> None:
    """A's token, A's org header, B's object IDs → never B's data."""
    a = tenants["a"]
    r = await call(control.client, route, b_ids(tenants), control.auth(a["token"], a["org"]["id"]))
    if "{" in route:
        assert r.status_code in (403, 404), f"{route} → {r.status_code} {r.text[:200]}"
    else:
        # Routes without IDs answer for A only: nothing from B may appear.
        assert r.status_code < 500
        for value in b_ids(tenants).values():
            if len(value) == 36:
                assert value not in r.text, f"{route} leaked a B identifier"
        assert tenants["b"]["org"]["tenant_id"] not in r.text


@pytest.mark.parametrize("route", sorted(r for r, c in CONTROL_ROUTES.items() if c == "tenant"))
async def test_tenant_route_with_b_org_header(control: Any, tenants: dict[str, Any], route: str) -> None:
    """A's token claiming B's org → 404 (membership check), for every tenant route."""
    a = tenants["a"]
    r = await call(control.client, route, b_ids(tenants), control.auth(a["token"], tenants["b"]["org"]["id"]))
    assert r.status_code == 404, f"{route} → {r.status_code} {r.text[:200]}"


@pytest.mark.parametrize("route", sorted(r for r, c in CONTROL_ROUTES.items() if c == "staff"))
async def test_staff_routes_reject_customer_tokens(control: Any, tenants: dict[str, Any], route: str) -> None:
    a = tenants["a"]
    r = await call(control.client, route, b_ids(tenants), control.auth(a["token"], a["org"]["id"]))
    assert r.status_code == 403, f"{route} → {r.status_code}"


@pytest.mark.parametrize("route", sorted(r for r, c in CONTROL_ROUTES.items() if c == "public"))
async def test_public_routes_serve_no_tenant_data(control: Any, tenants: dict[str, Any], route: str) -> None:
    r = await call(control.client, route, {"token": "y" * 43}, {})
    assert r.status_code < 500
    for t in (tenants["a"], tenants["b"]):
        assert t["org"]["id"] not in r.text and t["org"]["tenant_id"] not in r.text


async def test_user_routes_do_not_leak_other_tenants(control: Any, tenants: dict[str, Any]) -> None:
    me = await control.client.get("/v1/me", headers=control.auth(tenants["a"]["token"]))
    assert {m["org_id"] for m in me.json()["memberships"]} == {tenants["a"]["org"]["id"]}
    accept = await control.client.post(
        f"/v1/invites/{'y' * 43}/accept", headers=control.auth(tenants["a"]["token"])
    )
    assert accept.status_code == 404


async def test_victim_objects_unchanged(control: Any, tenants: dict[str, Any]) -> None:
    b = tenants["b"]
    hb = control.auth(b["token"], b["org"]["id"])
    org = (await control.client.get(f"/v1/orgs/{b['org']['id']}", headers=hb)).json()
    assert org["name"] == "Tenant B Victim"
    team = (await control.client.get(f"/v1/orgs/{b['org']['id']}/members", headers=hb)).json()
    assert any(i["id"] == b["invite"]["id"] and i["status"] == "pending" for i in team["invites"])
    assert next(m for m in team["members"] if m["id"] == b["membership"]["id"])["status"] == "active"
    notes = (await control.client.get("/v1/notifications", headers=hb)).json()
    assert next(n for n in notes["items"] if n["id"] == b["notification"]["id"])["read_at"] is None
    assert not any(i["email"] == "intruder@example.test" for i in team["invites"])


async def test_data_api_tenant_route(control: Any, data: Any, tenants: dict[str, Any]) -> None:
    a, b = tenants["a"], tenants["b"]
    mine = await data.client.get("/v1/tenant", headers=control.auth(a["token"], a["org"]["id"]))
    assert mine.status_code == 200, mine.text
    body = mine.json()
    assert body["database"] == a["org"]["tenant_id"]
    assert body["db_user"] == f"{a['org']['tenant_id']}_ro"
    assert "core" in body["schemas"] and body["cbm_version"] == "0.0"
    theirs = await data.client.get("/v1/tenant", headers=control.auth(a["token"], b["org"]["id"]))
    assert theirs.status_code == 404
    assert (await data.client.get("/v1/tenant", headers=control.auth(a["token"]))).status_code == 400
    staff = control.tokens.staff("staff-x", ["staff_admin"])
    assert (
        await data.client.get("/v1/tenant", headers=control.auth(staff, a["org"]["id"]))
    ).status_code == 403
    assert (await data.client.get("/v1/tenant")).status_code == 401
