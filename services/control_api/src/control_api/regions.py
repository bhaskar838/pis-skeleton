"""Country → data-residency region, from the editable world map (SPEC §4.1, §8.7; ADR-0012).

The map lives in the ``region`` and ``country`` tables (seeded from :mod:`control_api.world`) and is changed by
staff in the control panel. Rules:

* Sign-up is allowed only for a country with ``signup_enabled`` whose region is ``active``.
* A country can be enabled only while its region is active.
* A region cannot leave ``active`` while it has enabled countries or live tenants.
* Moving a country only affects new sign-ups; a tenant's region never changes (DB trigger ``org_region_immutable``).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from control_api import audit
from control_api.audit import Actor
from control_api.models import Country, Org, Region

RegionStatus = Literal["active", "planned", "disabled"]


class RegionRuleError(ValueError):
    """A change that would break a region rule (shown to staff as 409)."""


class CountryNotAvailableError(Exception):
    def __init__(self, code: str, name: str | None) -> None:
        super().__init__(code)
        self.code = code
        self.name = name


def normalise_country(country: str) -> str:
    code = country.strip().upper()
    if len(code) != 2 or not code.isalpha():
        raise ValueError("country must be an ISO 3166-1 alpha-2 code")
    return code


async def signup_region(session: AsyncSession, country: str) -> str:
    """The region a new organisation in ``country`` is created in, or :class:`CountryNotAvailableError`."""
    code = normalise_country(country)
    row = (
        await session.execute(
            select(Country.name, Country.region_code, Country.signup_enabled, Region.status)
            .join(Region, Region.code == Country.region_code)
            .where(Country.code == code)
        )
    ).one_or_none()
    if row is None:
        raise CountryNotAvailableError(code, None)
    if not row.signup_enabled or row.status != "active":
        raise CountryNotAvailableError(code, row.name)
    region: str = row.region_code
    return region


async def available_countries(session: AsyncSession) -> list[tuple[str, str, str]]:
    """(code, name, region) of every country open for sign-up, by name."""
    rows = await session.execute(
        select(Country.code, Country.name, Country.region_code)
        .join(Region, Region.code == Country.region_code)
        .where(Country.signup_enabled.is_(True), Region.status == "active")
        .order_by(Country.name)
    )
    return [(r.code, r.name, r.region_code) for r in rows]


@dataclass(frozen=True)
class RegionSummary:
    code: str
    name: str
    status: str
    sort: int
    countries: int
    enabled_countries: int
    live_tenants: int


async def region_summaries(session: AsyncSession) -> list[RegionSummary]:
    countries = dict(
        (await session.execute(select(Country.region_code, func.count()).group_by(Country.region_code)))
        .tuples()
        .all()
    )
    enabled = dict(
        (
            await session.execute(
                select(Country.region_code, func.count())
                .where(Country.signup_enabled.is_(True))
                .group_by(Country.region_code)
            )
        )
        .tuples()
        .all()
    )
    tenants = dict(
        (
            await session.execute(
                select(Org.region, func.count()).where(Org.status != "deleted").group_by(Org.region)
            )
        )
        .tuples()
        .all()
    )
    regions = (await session.scalars(select(Region).order_by(Region.sort, Region.code))).all()
    return [
        RegionSummary(
            r.code,
            r.name,
            r.status,
            r.sort,
            countries.get(r.code, 0),
            enabled.get(r.code, 0),
            tenants.get(r.code, 0),
        )
        for r in regions
    ]


async def create_region(session: AsyncSession, code: str, name: str, sort: int, actor: Actor) -> Region:
    if await session.get(Region, code) is not None:
        raise RegionRuleError(f"Region {code} already exists.")
    region = Region(code=code, name=name, status="planned", sort=sort, updated_by=_who(actor))
    session.add(region)
    await session.flush()
    await _audit(
        session, actor, "staff.region.created", code, {"name": name, "status": "planned", "sort": sort}
    )
    return region


async def update_region(
    session: AsyncSession,
    code: str,
    actor: Actor,
    *,
    name: str | None = None,
    status: RegionStatus | None = None,
    sort: int | None = None,
) -> Region:
    region = await session.get(Region, code, with_for_update=True)
    if region is None:
        raise LookupError(code)
    before = {"name": region.name, "status": region.status, "sort": region.sort}
    if status is not None and status != "active" and region.status == "active":
        enabled = await session.scalar(
            select(func.count())
            .select_from(Country)
            .where(Country.region_code == code, Country.signup_enabled.is_(True))
        )
        if enabled:
            raise RegionRuleError(
                f"{region.name} still has {enabled} countries open for sign-up. Close them first."
            )
        live = await session.scalar(
            select(func.count()).select_from(Org).where(Org.region == code, Org.status != "deleted")
        )
        if live:
            raise RegionRuleError(f"{region.name} still hosts {live} tenants; it cannot be switched off.")
    if name is not None:
        region.name = name
    if status is not None:
        region.status = status
    if sort is not None:
        region.sort = sort
    region.updated_by = _who(actor)
    after = {"name": region.name, "status": region.status, "sort": region.sort}
    if after != before:
        await _audit(session, actor, "staff.region.updated", code, {"before": before, "after": after})
    return region


async def update_country(
    session: AsyncSession,
    code: str,
    actor: Actor,
    *,
    region_code: str | None = None,
    signup_enabled: bool | None = None,
) -> Country:
    country = await session.get(Country, code, with_for_update=True)
    if country is None:
        raise LookupError(code)
    before = {"region": country.region_code, "signup_enabled": country.signup_enabled}
    target_region = region_code or country.region_code
    target_enabled = country.signup_enabled if signup_enabled is None else signup_enabled
    region = await session.get(Region, target_region)
    if region is None:
        raise RegionRuleError(f"Unknown region {target_region}.")
    if target_enabled and region.status != "active":
        raise RegionRuleError(
            f"{country.name} cannot be open for sign-up while {region.name} ({region.code}) is {region.status}. "
            "Activate the region first."
        )
    country.region_code = target_region
    country.signup_enabled = target_enabled
    country.updated_by = _who(actor)
    after = {"region": country.region_code, "signup_enabled": country.signup_enabled}
    if after != before:
        await _audit(session, actor, "staff.country.updated", code, {"before": before, "after": after})
    return country


async def _audit(
    session: AsyncSession, actor: Actor, action: str, target: str, details: dict[str, Any]
) -> None:
    await audit.emit(
        session,
        actor=actor,
        action=action,
        org_id=None,
        target_type="country" if action.startswith("staff.country") else "region",
        target_id=target,
        details=details,
    )


def _who(actor: Actor) -> str:
    return f"{actor.type}:{actor.id or '-'}"
