"""Unit tests: the default world map (ADR-0012) and the settings catalog (ADR-0011). No Docker."""

from __future__ import annotations

from typing import Any

import pytest

from control_api.config.catalog import CATALOG, SECTIONS, SETTINGS_BY_KEY, SettingValueError, validate
from control_api.settings import ControlSettings
from control_api.world import COUNTRIES, LAUNCH_COUNTRIES, REGIONS

REGION_CODES = {r[0] for r in REGIONS}
EU27 = frozenset(
    "AT BE BG HR CY CZ DK EE FI FR DE GR HU IE IT LV LT LU MT NL PL PT RO SK SI ES SE".split()  # noqa: SIM905
)


# ------------------------------------------------------------------------------------------ world map
def test_every_iso_country_has_exactly_one_known_region() -> None:
    assert len(COUNTRIES) == 250  # 249 ISO 3166-1 alpha-2 codes + XK
    assert {region for _, region in COUNTRIES.values()} == REGION_CODES
    assert all(len(code) == 2 and code.isupper() for code in COUNTRIES)
    assert all(name and name != code for code, (name, _) in COUNTRIES.items())


def test_four_regions_two_active_at_launch() -> None:
    assert len(REGIONS) == 4
    assert {c for c, _, status, _ in REGIONS if status == "active"} == {"ap-south-1", "eu-west-2"}


@pytest.mark.parametrize(
    ("country", "region"),
    [
        ("IN", "ap-south-1"),
        ("AE", "ap-south-1"),
        ("KE", "ap-south-1"),
        ("GB", "eu-west-2"),
        ("DE", "eu-west-2"),
        ("ZA", "eu-west-2"),
        ("TR", "eu-west-2"),
        ("US", "us-east-1"),
        ("BR", "us-east-1"),
        ("CA", "us-east-1"),
        ("SG", "ap-southeast-1"),
        ("JP", "ap-southeast-1"),
        ("AU", "ap-southeast-1"),
    ],
)
def test_nearest_region_defaults(country: str, region: str) -> None:
    assert COUNTRIES[country][1] == region


@pytest.mark.parametrize("country", ["RE", "GP", "MQ", "GF", "YT", "MF", "AX", "JE", "GG", "IM", "GI"])
def test_places_legally_in_eu_or_uk_stay_in_london(country: str) -> None:
    assert COUNTRIES[country][1] == "eu-west-2"


def test_launch_countries_are_india_and_legal_europe_in_active_regions() -> None:
    assert "IN" in LAUNCH_COUNTRIES and EU27 | {"GB", "NO", "IS", "LI", "CH"} <= LAUNCH_COUNTRIES
    assert not LAUNCH_COUNTRIES & {"US", "SG", "AE", "AU", "BR"}
    active = {c for c, _, status, _ in REGIONS if status == "active"}
    assert all(COUNTRIES[c][1] in active for c in LAUNCH_COUNTRIES)


# ---------------------------------------------------------------------------------------- catalog
def test_catalog_is_well_formed() -> None:
    assert len(SETTINGS_BY_KEY) == len(CATALOG)
    fields = set(ControlSettings.model_fields)
    for d in CATALOG:
        assert d.section in SECTIONS
        assert d.key.startswith(f"{d.section}.")
        assert d.env_attr is None or d.env_attr in fields, d.key
        if not d.is_secret:
            assert validate(d.key, d.default) == d.default, d.key  # defaults satisfy their own rules
        assert d.write_permission == ("platform:secrets:write" if d.is_secret else "platform:config:write")


def test_env_defaults_satisfy_the_catalog() -> None:
    s = ControlSettings()
    for d in CATALOG:
        if d.env_attr and not d.is_secret:
            raw = getattr(s, d.env_attr)
            validate(d.key, "" if raw is None else raw)


@pytest.mark.parametrize(
    ("key", "value", "expected"),
    [
        ("chassis.max_orgs_per_user", 5, 5),
        ("body.product_name", "  Kesari Insights ", "Kesari Insights"),
        ("body.support_email", "Help@Example.COM", "help@example.com"),
        ("body.terms_url", "", ""),
        ("body.terms_url", "https://example.com/terms", "https://example.com/terms"),
        ("electricals.smtp_starttls", True, True),
        ("electricals.mail_from", "Kesari <no-reply@kesari.in>", "Kesari <no-reply@kesari.in>"),
        ("trims.concierge_onboarding", "paid", "paid"),
        (
            "trims.concierge_onboarding_price",
            {"INR": "4999", "GBP": "49.5", "EUR": 59},
            {"INR": "4999.00", "GBP": "49.50", "EUR": "59.00"},
        ),
        ("electricals.smtp_password", "s3cret!", "s3cret!"),
    ],
)
def test_valid_values_are_normalised(key: str, value: Any, expected: Any) -> None:
    assert validate(key, value) == expected


@pytest.mark.parametrize(
    ("key", "value", "message"),
    [
        ("chassis.max_orgs_per_user", 0, "at least 1"),
        ("chassis.max_orgs_per_user", 101, "at most 100"),
        ("chassis.max_orgs_per_user", True, "whole number"),
        ("chassis.max_orgs_per_user", "3", "whole number"),
        ("chassis.deprovision_default_pending_days", 6, "at least 7"),
        ("body.product_name", "", "must not be empty"),
        ("body.product_name", "x" * 61, "at most 60"),
        ("body.product_name", "bad\nname", "control characters"),
        ("body.product_name", 42, "must be text"),
        ("body.support_email", "not-an-email", "e-mail address"),
        ("body.terms_url", "http://example.com", "https://"),
        ("body.terms_url", "javascript:alert(1)", "https://"),
        ("electricals.smtp_starttls", "yes", "true or false"),
        ("electricals.mail_from", "No Address", "Name <address"),
        ("trims.concierge_onboarding", "maybe", "one of"),
        ("trims.concierge_onboarding_price", {"JPY": "1"}, "currency"),
        ("trims.concierge_onboarding_price", {"INR": "-1"}, "between 0"),
        ("trims.concierge_onboarding_price", {"INR": "1.001"}, "2 decimals"),
        ("trims.concierge_onboarding_price", {"INR": "abc"}, "not a number"),
        ("trims.concierge_onboarding_price", {"INR": True}, "numbers written as text"),
        ("trims.concierge_onboarding_price", {"GBP": 49.5}, "numbers written as text"),
        ("trims.concierge_onboarding_price", ["INR"], "map of currency"),
        ("trims.concierge_onboarding_price", {"INR": "NaN"}, "between 0"),
        ("electricals.smtp_password", "", "1-4096"),
    ],
)
def test_invalid_values_are_rejected(key: str, value: Any, message: str) -> None:
    with pytest.raises(SettingValueError, match=message):
        validate(key, value)
