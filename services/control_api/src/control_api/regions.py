"""Country → data-residency region (SPEC §4.1 Regions, §8.7; OPEN_QUESTIONS Q3)."""

from __future__ import annotations

INDIA = "ap-south-1"
UK_EU = "eu-west-2"

# London (OPEN_QUESTIONS Q3, resolved): the UK with its Crown Dependencies and Gibraltar; the EU-27, including
# the outermost regions and Åland that ISO 3166 lists separately; the EEA (IS, LI, NO); Switzerland; and the
# European jurisdictions with an EU adequacy decision (Andorra, Faroe Islands).
_UK_EU_COUNTRIES = frozenset(
    {
        "GB",
        "GG",
        "JE",
        "IM",
        "GI",
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
        "AX",
        "GF",
        "GP",
        "MQ",
        "RE",
        "YT",
        "MF",
        "IS",
        "LI",
        "NO",
        "CH",
        "AD",
        "FO",
    }
)


def region_for_country(country: str) -> str:
    code = country.strip().upper()
    if len(code) != 2 or not code.isalpha():
        raise ValueError("country must be an ISO 3166-1 alpha-2 code")
    if code in _UK_EU_COUNTRIES:
        return UK_EU
    return INDIA  # India and every other country (Q3)
