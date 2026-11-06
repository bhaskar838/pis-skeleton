"""Country → data-residency region (SPEC §4.1 Regions, §8.7; OPEN_QUESTIONS Q3)."""

from __future__ import annotations

INDIA = "ap-south-1"
UK_EU = "eu-west-2"

# UK, EU-27, EEA (IS, LI, NO) and Switzerland → London.
_UK_EU_COUNTRIES = frozenset(
    {
        "GB",
        "AT",
        "BE",
        "BG",
        "HR",
        "CY",
        "CZ",
        "DK",
        "EE",
        "FI",
        "FR",
        "DE",
        "GR",
        "HU",
        "IE",
        "IT",
        "LV",
        "LT",
        "LU",
        "MT",
        "NL",
        "PL",
        "PT",
        "RO",
        "SK",
        "SI",
        "ES",
        "SE",
        "IS",
        "LI",
        "NO",
        "CH",
    }
)


def region_for_country(country: str) -> str:
    code = country.strip().upper()
    if len(code) != 2 or not code.isalpha():
        raise ValueError("country must be an ISO 3166-1 alpha-2 code")
    if code in _UK_EU_COUNTRIES:
        return UK_EU
    return INDIA  # India and, until decided otherwise (Q3), the rest of the world
