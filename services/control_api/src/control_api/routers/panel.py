"""Control panel API (``/v1/admin/config|secrets|regions|countries``), ADR-0011 / ADR-0012.

Staff only. Every change goes through :class:`ConfigRegistry` or :mod:`control_api.regions`, which validate it,
version it and append it to the platform audit chain. Secret values can be written but are never returned.
"""

from __future__ import annotations

from typing import Annotated, Any, cast

from fastapi import APIRouter, Depends, Query
from pydantic import SecretStr
from sqlalchemy import select

from control_api import regions as region_svc
from control_api.config import (
    SECTIONS,
    NotRevertibleError,
    SecretsUnavailableError,
    SettingState,
    SettingValueError,
    UnknownSettingError,
)
from control_api.config.catalog import DEPLOYMENT_OWNED
from control_api.deps import StaffContext, StateDep, staff_require
from control_api.models import Country
from control_api.schemas import (
    ConfigOut,
    ConfigSectionOut,
    CountryOut,
    CountryUpdate,
    DeploymentValueOut,
    RegionCreate,
    RegionOut,
    RegionUpdate,
    SecretUpdate,
    SettingHistoryOut,
    SettingOut,
    SettingUpdate,
)
from dcs_common.problem import PROBLEM_RESPONSES, ProblemError, conflict, forbidden, not_found

router = APIRouter(prefix="/v1/admin", tags=["admin: control panel"], responses=PROBLEM_RESPONSES)

ConfigRead = Annotated[StaffContext, Depends(staff_require("platform:config:read"))]
ConfigWrite = Annotated[StaffContext, Depends(staff_require("platform:config:write"))]
SecretsWrite = Annotated[StaffContext, Depends(staff_require("platform:secrets:write"))]
RegionsWrite = Annotated[StaffContext, Depends(staff_require("platform:regions:write"))]

KeyPath = Annotated[str, "setting key"]


def setting_out(st: SettingState) -> SettingOut:
    d = st.definition
    return SettingOut(
        key=d.key,
        section=d.section,
        label=d.label,
        help=d.help,
        type=d.type,
        value=None if d.is_secret else st.value,
        default=None if d.is_secret else d.default,
        source=st.source,
        is_set=st.is_set,
        version=st.version,
        updated_by=st.updated_by,
        updated_at=st.updated_at,
        min=d.min,
        max=d.max,
        choices=list(d.choices),
        optional=d.optional,
        public=d.public,
        used_from=d.used_from,
        write_permission=d.write_permission,
    )


def _invalid(label: str, exc: Exception) -> ProblemError:
    return ProblemError(422, slug="invalid-setting", detail=f"{label} {exc}")


def _unknown() -> ProblemError:
    return not_found()


# ------------------------------------------------------------------------------------------ settings
@router.get("/config", response_model=ConfigOut, summary="All control-panel settings by car section")
async def get_config(state: StateDep, ctx: ConfigRead) -> ConfigOut:
    states = await state.config.states()
    sections = [
        ConfigSectionOut(
            id=sid,
            name=name,
            description=desc,
            settings=[setting_out(s) for s in states if s.definition.section == sid],
        )
        for sid, (name, desc) in SECTIONS.items()
    ]
    deployment = []
    for dv in DEPLOYMENT_OWNED:
        raw: Any = getattr(state.settings, dv.attr)
        if isinstance(raw, SecretStr):
            raw = raw.get_secret_value()
        deployment.append(
            DeploymentValueOut(
                label=dv.label, is_set=bool(raw), value=str(raw) if dv.reveal and raw else None
            )
        )
    return ConfigOut(sections=sections, deployment=deployment)


@router.put("/config/{key}", response_model=SettingOut, summary="Set a setting's panel value")
async def put_setting(key: KeyPath, body: SettingUpdate, state: StateDep, ctx: ConfigWrite) -> SettingOut:
    try:
        d = state.config.definition(key)
    except UnknownSettingError:
        raise _unknown() from None
    if d.is_secret:
        raise ProblemError(
            422, slug="use-secrets-endpoint", detail="Secrets are set with PUT /v1/admin/secrets/{key}."
        )
    try:
        return setting_out(await state.config.set(key, body.value, ctx.actor))
    except SettingValueError as exc:
        raise _invalid(d.label, exc) from None


@router.delete("/config/{key}", response_model=SettingOut, summary="Remove the panel value (back to default)")
async def reset_setting(key: KeyPath, state: StateDep, ctx: ConfigWrite) -> SettingOut:
    try:
        d = state.config.definition(key)
    except UnknownSettingError:
        raise _unknown() from None
    if not ctx.has(d.write_permission):
        raise forbidden(permission=d.write_permission)
    return setting_out(await state.config.reset(key, ctx.actor))


@router.get("/config/{key}/history", response_model=list[SettingHistoryOut], summary="Change history")
async def setting_history(
    key: KeyPath, state: StateDep, ctx: ConfigRead, limit: Annotated[int, Query(ge=1, le=200)] = 50
) -> list[SettingHistoryOut]:
    try:
        rows = await state.config.history(key, limit)
    except UnknownSettingError:
        raise _unknown() from None
    return [
        SettingHistoryOut(
            version=r.version,
            action=cast(Any, r.action),
            value=r.value,
            changed_by=r.changed_by,
            changed_at=r.changed_at,
        )
        for r in rows
    ]


@router.post(
    "/config/{key}/revert/{version}", response_model=SettingOut, summary="Go back to an earlier value"
)
async def revert_setting(key: KeyPath, version: int, state: StateDep, ctx: ConfigWrite) -> SettingOut:
    try:
        d = state.config.definition(key)
        return setting_out(await state.config.revert(key, version, ctx.actor))
    except UnknownSettingError:
        raise _unknown() from None
    except NotRevertibleError as exc:
        raise conflict(str(exc)) from None
    except SettingValueError as exc:  # the old value no longer fits today's bounds
        raise _invalid(d.label, exc) from None
    except LookupError:
        raise _unknown() from None


# ------------------------------------------------------------------------------------------- secrets
@router.put("/secrets/{key}", response_model=SettingOut, summary="Set a secret (write-only)")
async def put_secret(key: KeyPath, body: SecretUpdate, state: StateDep, ctx: SecretsWrite) -> SettingOut:
    try:
        d = state.config.definition(key)
    except UnknownSettingError:
        raise _unknown() from None
    if not d.is_secret:
        raise ProblemError(
            422, slug="not-a-secret", detail=f"{d.label} is not a secret; use PUT /v1/admin/config."
        )
    try:
        return setting_out(await state.config.set_secret(key, body.value, ctx.actor))
    except SettingValueError as exc:
        raise _invalid(d.label, exc) from None
    except SecretsUnavailableError:
        raise ProblemError(
            503,
            slug="secrets-unavailable",
            detail="No key service is configured, so secrets cannot be stored.",
        ) from None


@router.delete("/secrets/{key}", response_model=SettingOut, summary="Clear a secret")
async def clear_secret(key: KeyPath, state: StateDep, ctx: SecretsWrite) -> SettingOut:
    try:
        d = state.config.definition(key)
    except UnknownSettingError:
        raise _unknown() from None
    if not d.is_secret:
        raise ProblemError(422, slug="not-a-secret", detail=f"{d.label} is not a secret.")
    return setting_out(await state.config.clear_secret(key, ctx.actor))


# ------------------------------------------------------------------------------- regions & countries
def _region_out(r: region_svc.RegionSummary) -> RegionOut:
    return RegionOut(
        code=r.code,
        name=r.name,
        status=cast(Any, r.status),
        sort=r.sort,
        countries=r.countries,
        enabled_countries=r.enabled_countries,
        live_tenants=r.live_tenants,
    )


async def _one_region(state: StateDep, code: str) -> RegionOut:
    async with state.db.platform_tx() as s:
        for r in await region_svc.region_summaries(s):
            if r.code == code:
                return _region_out(r)
    raise not_found()


@router.get("/regions", response_model=list[RegionOut], summary="Regions with country and tenant counts")
async def list_regions(state: StateDep, ctx: ConfigRead) -> list[RegionOut]:
    async with state.db.platform_tx() as s:
        return [_region_out(r) for r in await region_svc.region_summaries(s)]


@router.post(
    "/regions", status_code=201, response_model=RegionOut, summary="Add a region (starts as planned)"
)
async def create_region(body: RegionCreate, state: StateDep, ctx: RegionsWrite) -> RegionOut:
    try:
        async with state.db.platform_tx() as s:
            await region_svc.create_region(s, body.code, body.name, body.sort, ctx.actor)
    except region_svc.RegionRuleError as exc:
        raise conflict(str(exc)) from None
    return await _one_region(state, body.code)


@router.patch(
    "/regions/{code}", response_model=RegionOut, summary="Rename, re-order or (de)activate a region"
)
async def update_region(code: str, body: RegionUpdate, state: StateDep, ctx: RegionsWrite) -> RegionOut:
    try:
        async with state.db.platform_tx() as s:
            await region_svc.update_region(
                s, code, ctx.actor, name=body.name, status=body.status, sort=body.sort
            )
    except LookupError:
        raise not_found() from None
    except region_svc.RegionRuleError as exc:
        raise conflict(str(exc)) from None
    return await _one_region(state, code)


@router.get("/countries", response_model=list[CountryOut], summary="The country → region map (all countries)")
async def list_countries(
    state: StateDep,
    ctx: ConfigRead,
    region: Annotated[str | None, Query(max_length=30)] = None,
    enabled: bool | None = None,
    q: Annotated[str | None, Query(max_length=60)] = None,
) -> list[CountryOut]:
    stmt = select(Country).order_by(Country.name)
    if region:
        stmt = stmt.where(Country.region_code == region)
    if enabled is not None:
        stmt = stmt.where(Country.signup_enabled.is_(enabled))
    if q:
        like = f"%{q.replace('%', '').replace('_', '')}%"
        stmt = stmt.where(Country.name.ilike(like) | Country.code.ilike(like))
    async with state.db.platform_tx() as s:
        rows = (await s.scalars(stmt)).all()
    return [
        CountryOut(code=c.code, name=c.name, region=c.region_code, signup_enabled=c.signup_enabled)
        for c in rows
    ]


@router.patch("/countries/{code}", response_model=CountryOut, summary="Move a country or open/close sign-up")
async def update_country(code: str, body: CountryUpdate, state: StateDep, ctx: RegionsWrite) -> CountryOut:
    try:
        async with state.db.platform_tx() as s:
            c = await region_svc.update_country(
                s, code.upper(), ctx.actor, region_code=body.region, signup_enabled=body.signup_enabled
            )
            out = CountryOut(code=c.code, name=c.name, region=c.region_code, signup_enabled=c.signup_enabled)
    except LookupError:
        raise not_found() from None
    except region_svc.RegionRuleError as exc:
        raise conflict(str(exc)) from None
    return out
