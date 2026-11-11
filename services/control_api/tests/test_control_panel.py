"""Integration: the control panel (Phase 0.5, ADR-0011 / ADR-0012) against real Postgres.

Covers settings (validation, history, revert, audit, live effect), write-only secrets, staff permissions,
the world map with sign-up gating and region rules, and the public brand / countries endpoints.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

import pytest
from sqlalchemy import select, update

from control_api.config import ConfigRegistry
from control_api.config.catalog import CATALOG, SECTIONS
from control_api.mailer import Mail, SmtpMailer
from control_api.models import Country, PlatformSecret
from control_api.world import COUNTRIES, LAUNCH_COUNTRIES

pytestmark = pytest.mark.integration

SECRET = "pa55-Very-Secret-Value-4242"


def staff(control: Any, role: str, *, mfa: bool = True) -> dict[str, str]:
    return control.auth(control.tokens.staff(f"{role}-panel", [role], mfa=mfa))


@pytest.fixture
async def clean_panel(control: Any) -> AsyncIterator[None]:
    """Panel state is shared by the session: put every setting and country back afterwards."""
    yield
    actor = _system_actor()
    for d in CATALOG:
        await control.state.config.reset(d.key, actor)
    async with control.state.db.platform_tx() as s:
        for code, (_, region) in COUNTRIES.items():
            await s.execute(
                update(Country)
                .where(Country.code == code)
                .values(region_code=region, signup_enabled=code in LAUNCH_COUNTRIES)
            )
    control.state.config.invalidate()


def _system_actor() -> Any:
    from control_api.audit import Actor

    return Actor("system", "test-cleanup")


# ------------------------------------------------------------------------------------------ settings
async def test_config_lists_every_car_section_and_hides_secrets(control: Any, clean_panel: None) -> None:
    r = await control.client.get("/v1/admin/config", headers=staff(control, "staff_admin"))
    assert r.status_code == 200, r.text
    body = r.json()
    assert [s["id"] for s in body["sections"]] == list(SECTIONS)
    settings = {s["key"]: s for sec in body["sections"] for s in sec["settings"]}
    assert set(settings) == {d.key for d in CATALOG}
    assert settings["body.product_name"]["value"] == "DCS-PIS"
    assert settings["body.product_name"]["source"] == "default"
    assert settings["electricals.smtp_password"]["value"] is None
    assert settings["electricals.smtp_password"]["write_permission"] == "platform:secrets:write"
    deployment = {d["label"]: d for d in body["deployment"]}
    assert deployment["Control database URL"] == {
        "label": "Control database URL",
        "is_set": True,
        "value": None,
    }
    assert deployment["Environment"]["value"] == control.settings.env
    assert "dcs_control_app" not in r.text  # no connection strings leak


async def test_set_validate_history_revert_reset_and_audit(control: Any, clean_panel: None) -> None:
    h = staff(control, "staff_admin")
    key = "body.product_name"
    bad = await control.client.put(f"/v1/admin/config/{key}", json={"value": ""}, headers=h)
    assert bad.status_code == 422 and bad.json()["type"].endswith("invalid-setting")
    assert "Product name must not be empty" in bad.json()["detail"]

    v1 = await control.client.put(f"/v1/admin/config/{key}", json={"value": "Kesari Insights"}, headers=h)
    assert v1.status_code == 200, v1.text
    n = v1.json()["version"]  # versions keep counting for the whole session (history is append-only)
    assert (v1.json()["value"], v1.json()["source"]) == ("Kesari Insights", "panel")
    assert v1.json()["updated_by"] == "staff:staff_admin-panel"
    v2 = await control.client.put(f"/v1/admin/config/{key}", json={"value": "Kesari Two"}, headers=h)
    assert v2.json()["version"] == n + 1

    back = await control.client.post(f"/v1/admin/config/{key}/revert/{n}", headers=h)
    assert (
        back.status_code == 200
        and back.json()["value"] == "Kesari Insights"
        and back.json()["version"] == n + 2
    )
    hist = (await control.client.get(f"/v1/admin/config/{key}/history", headers=h)).json()
    assert [(e["version"], e["action"], e["value"]) for e in hist][:3] == [
        (n + 2, "revert", "Kesari Insights"),
        (n + 1, "set", "Kesari Two"),
        (n, "set", "Kesari Insights"),
    ]

    reset = await control.client.delete(f"/v1/admin/config/{key}", headers=h)
    assert reset.json()["source"] == "default" and reset.json()["value"] == "DCS-PIS"
    nope = await control.client.post(f"/v1/admin/config/{key}/revert/{n + 3}", headers=h)
    assert nope.status_code == 409  # a reset has no value to go back to
    assert (
        await control.client.post(f"/v1/admin/config/{key}/revert/{n + 99}", headers=h)
    ).status_code == 404
    assert (
        await control.client.put("/v1/admin/config/no.such", json={"value": 1}, headers=h)
    ).status_code == 404

    audit = (await control.client.get("/v1/admin/audit", params={"platform_only": True}, headers=h)).json()
    actions = [e for e in audit["items"] if e["target_id"] == key]
    assert {e["action"] for e in actions} >= {"staff.config.set", "staff.config.revert", "staff.config.reset"}
    first = next(e for e in reversed(actions) if e["action"] == "staff.config.set")
    assert first["details"]["new"] == "Kesari Insights" and first["details"]["old"] == "DCS-PIS"


async def test_panel_values_take_effect_without_restart(control: Any, clean_panel: None) -> None:
    h = staff(control, "staff_admin")
    owner, org = await control.signup("Limit Probe")
    r = await control.client.put("/v1/admin/config/chassis.max_orgs_per_user", json={"value": 1}, headers=h)
    assert r.status_code == 200
    second = await control.client.post(
        "/v1/orgs", json={"name": "Second", "country": "IN"}, headers=control.auth(owner)
    )
    assert second.status_code == 409 and second.json()["type"].endswith("org-limit")

    await control.client.put(
        "/v1/admin/config/body.product_name", json={"value": "Kesari Insights"}, headers=h
    )
    await control.client.put("/v1/admin/config/chassis.invite_ttl_days", json={"value": 2}, headers=h)
    inv = await control.client.post(
        f"/v1/orgs/{org['id']}/invites",
        json={"email": "ttl@example.test", "role": "viewer"},
        headers=control.auth(owner, org["id"]),
    )
    assert inv.status_code == 201, inv.text
    mail = control.state.mailer.sent[-1]
    assert mail.subject == "You're invited to Limit Probe on Kesari Insights"
    assert "expires in 2 days" in mail.text


async def test_other_processes_see_changes_within_the_cache_ttl(control: Any, clean_panel: None) -> None:
    now = [0.0]
    other = ConfigRegistry(control.state.db, control.settings, lambda: None, ttl_s=3.0, clock=lambda: now[0])
    assert await other.get_str("body.product_name") == "DCS-PIS"
    await control.client.put(
        "/v1/admin/config/body.product_name", json={"value": "Renamed"}, headers=staff(control, "staff_admin")
    )
    now[0] = 2.9
    assert await other.get_str("body.product_name") == "DCS-PIS"  # still cached
    now[0] = 3.1
    assert await other.get_str("body.product_name") == "Renamed"


async def test_smtp_mailer_reads_the_panel(
    control: Any, clean_panel: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    import aiosmtplib

    sent: list[tuple[Any, dict[str, Any]]] = []

    async def fake_send(msg: Any, **kw: Any) -> None:
        sent.append((msg, kw))

    monkeypatch.setattr(aiosmtplib, "send", fake_send)
    h = staff(control, "staff_admin")
    for key, value in {
        "electricals.smtp_host": "email-smtp.ap-south-1.amazonaws.com",
        "electricals.smtp_port": 587,
        "electricals.smtp_username": "AKIAEXAMPLE",
        "electricals.smtp_starttls": True,
        "electricals.mail_from": "Kesari <no-reply@kesari.example>",
        "body.product_name": "Kesari",
    }.items():
        assert (
            await control.client.put(f"/v1/admin/config/{key}", json={"value": value}, headers=h)
        ).status_code == 200
    assert (
        await control.client.put(
            "/v1/admin/secrets/electricals.smtp_password", json={"value": SECRET}, headers=h
        )
    ).status_code == 200
    await SmtpMailer(control.state.config).send(
        Mail("x@example.test", "{product}: hello", "Welcome to {product}")
    )
    msg, kw = sent[0]
    assert msg["From"] == "Kesari <no-reply@kesari.example>" and msg["Subject"] == "Kesari: hello"
    assert "Welcome to Kesari" in msg.get_content()
    assert kw == {
        "hostname": "email-smtp.ap-south-1.amazonaws.com",
        "port": 587,
        "username": "AKIAEXAMPLE",
        "password": SECRET,
        "start_tls": True,
        "timeout": 10,
    }


# ------------------------------------------------------------------------------------------- secrets
async def test_secrets_are_write_only(control: Any, clean_panel: None) -> None:
    admin, ops = staff(control, "staff_admin"), staff(control, "staff_ops")
    key = "electricals.smtp_password"
    assert (
        await control.client.put(f"/v1/admin/secrets/{key}", json={"value": SECRET}, headers=ops)
    ).status_code == 403
    assert (await control.client.delete(f"/v1/admin/config/{key}", headers=ops)).status_code == 403
    wrong = await control.client.put(f"/v1/admin/config/{key}", json={"value": SECRET}, headers=admin)
    assert wrong.status_code == 422 and wrong.json()["type"].endswith("use-secrets-endpoint")
    not_secret = await control.client.put(
        "/v1/admin/secrets/body.product_name", json={"value": "x"}, headers=admin
    )
    assert not_secret.status_code == 422

    put = await control.client.put(f"/v1/admin/secrets/{key}", json={"value": SECRET}, headers=admin)
    assert put.status_code == 200, put.text
    assert put.json()["value"] is None and put.json()["is_set"]
    n = put.json()["version"]
    responses = [
        put,
        await control.client.get("/v1/admin/config", headers=admin),
        await control.client.get(f"/v1/admin/config/{key}/history", headers=admin),
        await control.client.get("/v1/admin/audit", params={"platform_only": True}, headers=admin),
    ]
    for resp in responses:
        assert SECRET not in resp.text
    assert await control.state.config.secret(key) == SECRET
    async with control.state.db.platform_tx() as s:
        row = await s.scalar(select(PlatformSecret).where(PlatformSecret.key == key))
    assert row is not None and SECRET.encode() not in row.ciphertext and row.key_ref

    rotated = await control.client.put(f"/v1/admin/secrets/{key}", json={"value": "rotated"}, headers=admin)
    assert rotated.json()["version"] == n + 1 and await control.state.config.secret(key) == "rotated"
    cleared = await control.client.delete(f"/v1/admin/secrets/{key}", headers=admin)
    assert cleared.json()["is_set"] is False and await control.state.config.secret(key) is None
    hist = (await control.client.get(f"/v1/admin/config/{key}/history", headers=admin)).json()
    assert [(e["action"], e["value"]) for e in hist][:3] == [
        ("secret_cleared", None),
        ("secret_set", None),
        ("secret_set", None),
    ]
    revert = await control.client.post(f"/v1/admin/config/{key}/revert/{n}", headers=admin)
    assert revert.status_code == 409


async def test_staff_permissions(control: Any, clean_panel: None) -> None:
    support, ops, admin = (staff(control, r) for r in ("staff_support", "staff_ops", "staff_admin"))
    assert (await control.client.get("/v1/admin/config", headers=support)).status_code == 200
    put = {"value": "Ops Name"}
    assert (
        await control.client.put("/v1/admin/config/body.product_name", json=put, headers=support)
    ).status_code == 403
    assert (
        await control.client.put("/v1/admin/config/body.product_name", json=put, headers=ops)
    ).status_code == 200
    assert (
        await control.client.patch("/v1/admin/regions/us-east-1", json={"status": "active"}, headers=ops)
    ).status_code == 403
    assert (
        await control.client.patch("/v1/admin/countries/US", json={"signup_enabled": True}, headers=ops)
    ).status_code == 403
    no_mfa = staff(control, "staff_admin", mfa=False)
    assert (await control.client.get("/v1/admin/config", headers=no_mfa)).status_code == 403
    assert (await control.client.get("/v1/admin/regions", headers=admin)).status_code == 200


# --------------------------------------------------------------------------------- world map & sign-up
async def test_signup_follows_the_country_map(control: Any, clean_panel: None) -> None:
    admin = staff(control, "staff_admin")
    token, _ = await control.user(mfa=True)
    refused = await control.client.post(
        "/v1/orgs", json={"name": "Rio Co", "country": "BR"}, headers=control.auth(token)
    )
    assert refused.status_code == 422
    assert refused.json()["type"].endswith("country-not-available")
    assert refused.json()["detail"] == "DCS-PIS is not available in Brazil yet."

    created = await control.client.post(
        "/v1/admin/regions", json={"code": "sa-east-1", "name": "São Paulo", "sort": 50}, headers=admin
    )
    assert created.status_code == 201 and created.json()["status"] == "planned"
    dup = await control.client.post(
        "/v1/admin/regions", json={"code": "sa-east-1", "name": "Again"}, headers=admin
    )
    assert dup.status_code == 409
    moved = await control.client.patch("/v1/admin/countries/BR", json={"region": "sa-east-1"}, headers=admin)
    assert moved.status_code == 200 and moved.json() == {
        "code": "BR",
        "name": "Brazil",
        "region": "sa-east-1",
        "signup_enabled": False,
    }
    early = await control.client.patch("/v1/admin/countries/BR", json={"signup_enabled": True}, headers=admin)
    assert early.status_code == 409 and "Activate the region first" in early.json()["detail"]

    active = await control.client.patch(
        "/v1/admin/regions/sa-east-1", json={"status": "active"}, headers=admin
    )
    assert active.status_code == 200
    assert (
        await control.client.patch("/v1/admin/countries/BR", json={"signup_enabled": True}, headers=admin)
    ).status_code == 200
    public = (await control.client.get("/v1/public/countries")).json()
    assert {"code": "BR", "name": "Brazil", "region": "sa-east-1"} in public

    ok = await control.client.post(
        "/v1/orgs", json={"name": "Rio Co", "country": "BR"}, headers=control.auth(token)
    )
    assert ok.status_code == 201, ok.text
    assert ok.json()["region"] == "sa-east-1"

    busy = await control.client.patch(
        "/v1/admin/regions/sa-east-1", json={"status": "planned"}, headers=admin
    )
    assert busy.status_code == 409 and "countries open for sign-up" in busy.json()["detail"]
    await control.client.patch("/v1/admin/countries/BR", json={"signup_enabled": False}, headers=admin)
    hosting = await control.client.patch(
        "/v1/admin/regions/sa-east-1", json={"status": "planned"}, headers=admin
    )
    assert hosting.status_code == 409 and "hosts 1 tenants" in hosting.json()["detail"]

    regions = {r["code"]: r for r in (await control.client.get("/v1/admin/regions", headers=admin)).json()}
    assert regions["sa-east-1"]["live_tenants"] == 1 and regions["sa-east-1"]["countries"] == 1
    assert regions["ap-south-1"]["status"] == "active" and regions["us-east-1"]["status"] == "planned"
    assert (
        await control.client.patch("/v1/admin/regions/xx-none-1", json={"name": "x"}, headers=admin)
    ).status_code == 404
    assert (
        await control.client.patch("/v1/admin/countries/QQ", json={"signup_enabled": True}, headers=admin)
    ).status_code == 404
    unknown = await control.client.patch(
        "/v1/admin/countries/BR", json={"region": "xx-none-1"}, headers=admin
    )
    assert unknown.status_code == 409

    europe = (
        await control.client.get(
            "/v1/admin/countries", params={"region": "eu-west-2", "enabled": True}, headers=admin
        )
    ).json()
    assert {c["code"] for c in europe} == {c for c in LAUNCH_COUNTRIES if c != "IN"}
    search = (await control.client.get("/v1/admin/countries", params={"q": "ind"}, headers=admin)).json()
    assert "IN" in {c["code"] for c in search}


async def test_public_endpoints(control: Any, clean_panel: None) -> None:
    brand = await control.client.get("/v1/public/brand")
    assert brand.status_code == 200 and brand.headers["cache-control"] == "public, max-age=30"
    assert brand.json() == {
        "product_name": "DCS-PIS",
        "support_email": "support@dcs-pis.local",
        "terms_url": "",
        "privacy_url": "",
    }
    countries = {c["code"]: c for c in (await control.client.get("/v1/public/countries")).json()}
    assert set(countries) == LAUNCH_COUNTRIES
    assert countries["IN"]["region"] == "ap-south-1" and countries["GB"]["region"] == "eu-west-2"
    assert json.dumps(countries).count("us-east-1") == 0
