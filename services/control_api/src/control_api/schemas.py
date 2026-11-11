"""Public API models (OpenAPI → generated TS client via ``make codegen``)."""

from __future__ import annotations

import re
import uuid
from datetime import datetime
from typing import Any, Generic, Literal, TypeVar
from zoneinfo import available_timezones

from pydantic import BaseModel, ConfigDict, Field, field_validator

CustomerRole = Literal["owner", "admin", "data_manager", "analyst", "viewer", "billing"]
_EMAIL_RE = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,255}\.[A-Za-z]{2,}$")

T = TypeVar("T")


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Page(BaseModel, Generic[T]):
    items: list[T]
    next_cursor: str | None = None


# ------------------------------------------------------------------------------------------ me / orgs
class UserOut(BaseModel):
    id: uuid.UUID
    email: str
    name: str | None


class MembershipSummary(BaseModel):
    membership_id: uuid.UUID
    org_id: uuid.UUID
    org_name: str
    org_slug: str
    org_status: str
    tenant_id: str
    region: str
    role: CustomerRole
    permissions: list[str]
    mfa_required: bool


class MeOut(BaseModel):
    user: UserOut
    session_mfa: bool
    email_verified: bool
    memberships: list[MembershipSummary]


class OrgCreate(Strict):
    name: str = Field(min_length=1, max_length=200)
    country: str = Field(min_length=2, max_length=2, description="ISO 3166-1 alpha-2; fixes the data region")

    @field_validator("name")
    @classmethod
    def _strip(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("name must not be blank")
        return v

    @field_validator("country")
    @classmethod
    def _country(cls, v: str) -> str:
        if not v.isalpha():
            raise ValueError("country must be two letters")
        return v.upper()


class BusinessProfile(Strict):
    """Business profile (edited in G-01 now, collected in O-01 from Phase 1)."""

    industry: str | None = Field(default=None, max_length=100)
    business_model: str | None = Field(default=None, max_length=100)
    customer_type: Literal["B2B", "B2C", "both"] | None = None
    size_band: Literal["1-10", "11-50", "51-200", "201-1000", "1000+"] | None = None
    locations: int | None = Field(default=None, ge=0, le=100_000)
    currency: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")
    fiscal_year_start: str | None = Field(default=None, pattern=r"^(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])$")
    timezone: str | None = None
    goals: list[str] = Field(default_factory=list, max_length=20)

    @field_validator("timezone")
    @classmethod
    def _tz(cls, v: str | None) -> str | None:
        if v is not None and v not in available_timezones():
            raise ValueError("unknown IANA timezone")
        return v


class OrgOut(BaseModel):
    id: uuid.UUID
    tenant_id: str
    name: str
    slug: str
    country: str
    region: str
    status: str
    plan_id: str | None
    business_profile: dict[str, Any]
    profile_version: int
    created_at: datetime


class OrgProfilePatch(Strict):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    business_profile: BusinessProfile | None = None


# --------------------------------------------------------------------------------------- team
class MemberOut(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    email: str
    name: str | None
    role: CustomerRole
    status: str
    created_at: datetime


class InviteCreate(Strict):
    email: str = Field(max_length=320)
    role: CustomerRole

    @field_validator("email")
    @classmethod
    def _email(cls, v: str) -> str:
        v = v.strip().lower()
        if not _EMAIL_RE.fullmatch(v):
            raise ValueError("invalid e-mail address")
        return v


class InviteOut(BaseModel):
    id: uuid.UUID
    email: str
    role: CustomerRole
    status: str
    expires_at: datetime
    created_at: datetime


class TeamOut(BaseModel):
    members: list[MemberOut]
    invites: list[InviteOut]


class InvitePreview(BaseModel):
    org_name: str
    role: CustomerRole
    email_hint: str
    status: Literal["pending", "expired"]
    expires_at: datetime


class MembershipPatch(Strict):
    role: CustomerRole


# ---------------------------------------------------------------------------------------- audit
class AuditEventOut(BaseModel):
    id: int
    ts: datetime
    org_id: uuid.UUID | None
    actor_type: str
    actor_id: str | None
    action: str
    target_type: str | None
    target_id: str | None
    ip: str | None
    details: dict[str, Any]


# -------------------------------------------------------------------------------- notifications
class NotificationOut(BaseModel):
    id: uuid.UUID
    type: str
    payload: dict[str, Any]
    read_at: datetime | None
    created_at: datetime


class NotificationPref(Strict):
    event_type: str
    email: bool
    in_app: bool


class NotificationPrefsOut(BaseModel):
    items: list[NotificationPref]
    event_types: dict[str, str]


class NotificationPrefsIn(Strict):
    items: list[NotificationPref] = Field(max_length=100)


# ------------------------------------------------------------------------------- flags / security
class FlagsOut(BaseModel):
    flags: dict[str, Any]


class SecuritySummary(BaseModel):
    mfa_required_roles: list[str]
    your_role_requires_mfa: bool
    session_mfa: bool
    account_console_url: str


# ---------------------------------------------------------------------------------------- admin
class TenantRow(BaseModel):
    org_id: uuid.UUID
    tenant_id: str
    name: str
    slug: str
    region: str
    status: str
    plan_id: str | None
    db_status: str | None
    created_at: datetime


class TenantDetail(BaseModel):
    org: OrgOut
    db: dict[str, Any] | None
    key: dict[str, Any] | None
    member_count: int
    owners: list[str]
    recent_audit: list[AuditEventOut]


class StaffMeOut(BaseModel):
    subject: str
    email: str | None
    name: str | None
    roles: list[str]
    permissions: list[str]
    session_mfa: bool


class DeprovisionRequest(Strict):
    confirm_slug: str
    reason: str = Field(min_length=3, max_length=500)
    pending_days: int | None = Field(
        default=None,
        ge=7,
        le=30,
        description="Omit to use the panel default (chassis.deprovision_default_pending_days)",
    )


class WorkflowStarted(BaseModel):
    workflow_id: str


class DashboardOut(BaseModel):
    tenants_by_status: dict[str, int]
    tenants_by_region: dict[str, int]
    users: int
    audit_chains_failing: int
    last_verification_at: datetime | None


class VerificationRunOut(BaseModel):
    chain: uuid.UUID
    ran_at: datetime
    ok: bool
    checked: int
    first_bad_id: int | None
    reason: str | None


class FlagRow(BaseModel):
    key: str
    scope: Literal["global", "plan", "org"]
    scope_id: str
    value: Any
    updated_by: str | None
    updated_at: datetime


class FlagUpsert(Strict):
    key: str = Field(pattern=r"^[a-z][a-z0-9_.-]{1,63}$")
    scope: Literal["global", "plan", "org"]
    scope_id: str = Field(default="", max_length=64)
    value: Any


# ------------------------------------------------------------------------------- control panel (P0.5)
SettingSource = Literal["panel", "environment", "default"]


class SettingOut(BaseModel):
    key: str
    section: str
    label: str
    help: str
    type: Literal["string", "int", "bool", "enum", "email", "url", "money", "secret"]
    value: Any = Field(description="Effective value; always null for secrets")
    default: Any
    source: SettingSource
    is_set: bool
    version: int = Field(description="0 when no panel value is set")
    updated_by: str | None
    updated_at: datetime | None
    min: int | None
    max: int | None
    choices: list[str]
    optional: bool
    public: bool
    used_from: str
    write_permission: str


class ConfigSectionOut(BaseModel):
    id: str
    name: str
    description: str
    settings: list[SettingOut]


class DeploymentValueOut(BaseModel):
    label: str
    is_set: bool
    value: str | None = Field(description="Shown only for values that are not sensitive")


class ConfigOut(BaseModel):
    sections: list[ConfigSectionOut]
    deployment: list[DeploymentValueOut]


class SettingUpdate(Strict):
    value: Any


class SecretUpdate(Strict):
    value: str = Field(min_length=1, max_length=4096)


class SettingHistoryOut(BaseModel):
    version: int
    action: Literal["set", "reset", "revert", "secret_set", "secret_cleared"]
    value: Any
    changed_by: str
    changed_at: datetime


RegionStatusLiteral = Literal["active", "planned", "disabled"]


class RegionOut(BaseModel):
    code: str
    name: str
    status: RegionStatusLiteral
    sort: int
    countries: int
    enabled_countries: int
    live_tenants: int


class RegionCreate(Strict):
    code: str = Field(
        pattern=r"^[a-z]{2}(-gov)?-[a-z]+-[0-9]$", description="AWS region code, e.g. sa-east-1"
    )
    name: str = Field(min_length=1, max_length=60)
    sort: int = Field(default=100, ge=0, le=10000)


class RegionUpdate(Strict):
    name: str | None = Field(default=None, min_length=1, max_length=60)
    status: RegionStatusLiteral | None = None
    sort: int | None = Field(default=None, ge=0, le=10000)


class CountryOut(BaseModel):
    code: str
    name: str
    region: str
    signup_enabled: bool


class CountryUpdate(Strict):
    region: str | None = Field(default=None, pattern=r"^[a-z]{2}(-gov)?-[a-z]+-[0-9]$")
    signup_enabled: bool | None = None


class PublicBrandOut(BaseModel):
    product_name: str
    support_email: str
    terms_url: str
    privacy_url: str


class PublicCountryOut(BaseModel):
    code: str
    name: str
    region: str
