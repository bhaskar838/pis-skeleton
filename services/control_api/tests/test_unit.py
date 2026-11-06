"""Pure unit tests for control-api helpers (no Docker)."""

from __future__ import annotations

import base64
import hashlib
import hmac

import pytest
from pydantic import ValidationError

from control_api.idempotency import validate_key
from control_api.infra.scram import scram_sha256_verifier
from control_api.realtime import MemoryPublisher, org_channel, user_channel
from control_api.regions import INDIA, UK_EU, region_for_country
from control_api.routers.orgs import slugify
from control_api.schemas import BusinessProfile, InviteCreate, OrgCreate
from dcs_common.problem import ProblemError


@pytest.mark.parametrize(
    ("country", "region"),
    [
        ("IN", INDIA),
        ("in", INDIA),
        ("GB", UK_EU),
        ("DE", UK_EU),
        ("CH", UK_EU),
        ("NO", UK_EU),
        ("US", INDIA),
        ("SG", INDIA),
    ],
)
def test_region_for_country(country: str, region: str) -> None:
    assert region_for_country(country) == region


@pytest.mark.parametrize("bad", ["", "I", "IND", "1N"])
def test_region_rejects_bad_codes(bad: str) -> None:
    with pytest.raises(ValueError, match="ISO 3166"):
        region_for_country(bad)


def test_scram_verifier_matches_rfc7677_derivation() -> None:
    salt = b"0123456789abcdef"
    v = scram_sha256_verifier("pencil", salt=salt, iterations=4096)
    algo, rest = v.split("$", 1)
    iters_salt, keys = rest.split("$")
    iters, salt_b64 = iters_salt.split(":")
    stored_b64, server_b64 = keys.split(":")
    assert algo == "SCRAM-SHA-256" and iters == "4096"
    assert base64.b64decode(salt_b64) == salt
    salted = hashlib.pbkdf2_hmac("sha256", b"pencil", salt, 4096)
    client_key = hmac.new(salted, b"Client Key", hashlib.sha256).digest()
    assert base64.b64decode(stored_b64) == hashlib.sha256(client_key).digest()
    assert base64.b64decode(server_b64) == hmac.new(salted, b"Server Key", hashlib.sha256).digest()
    assert "pencil" not in v
    assert scram_sha256_verifier("pencil") != scram_sha256_verifier("pencil")  # random salt


def test_slugify() -> None:
    s = slugify("Northwind Fitness & Co.")
    assert s.startswith("northwind-fitness-co-") and len(s) == len("northwind-fitness-co-") + 4
    assert slugify("!!!").startswith("org-")


@pytest.mark.parametrize(
    ("key", "ok"),
    [
        (None, True),
        ("abcdefgh", True),
        ("a.b-c_d12", True),
        ("short", False),
        ("bad key!", False),
        ("x" * 129, False),
    ],
)
def test_idempotency_key(key: str | None, ok: bool) -> None:
    if ok:
        assert validate_key(key) == key
    else:
        with pytest.raises(ProblemError):
            validate_key(key)


def test_org_create_validation() -> None:
    assert OrgCreate(name="  Kesari  ", country="in").model_dump() == {"name": "Kesari", "country": "IN"}
    with pytest.raises(ValidationError):
        OrgCreate(name="   ", country="IN")
    with pytest.raises(ValidationError):
        OrgCreate(name="X", country="1N")


def test_business_profile_validation() -> None:
    p = BusinessProfile(
        currency="INR", timezone="Asia/Kolkata", fiscal_year_start="04-01", customer_type="B2C"
    )
    assert p.currency == "INR"
    for bad in (
        {"currency": "inr"},
        {"timezone": "Nowhere/City"},
        {"fiscal_year_start": "13-01"},
        {"unknown": 1},
        {"locations": -1},
    ):
        with pytest.raises(ValidationError):
            BusinessProfile(**bad)  # type: ignore[arg-type]


def test_invite_email_normalised() -> None:
    assert InviteCreate(email=" Asha@Example.COM ", role="analyst").email == "asha@example.com"
    with pytest.raises(ValidationError):
        InviteCreate(email="not-an-email", role="analyst")
    with pytest.raises(ValidationError):
        InviteCreate(email="a@b.co", role="superuser")  # type: ignore[arg-type]


async def test_channels_and_memory_publisher() -> None:
    import uuid

    assert org_channel("t_abcdefghij") == "t:t_abcdefghij:events"
    with pytest.raises(ValueError, match="tenant"):
        org_channel("t:*")
    uid = uuid.UUID(int=1)
    assert user_channel(uid) == f"u:{uid}:events"
    pub = MemoryPublisher()
    await pub.publish("c", {"a": 1})
    await pub.close()
    assert pub.events == [("c", {"a": 1})]
