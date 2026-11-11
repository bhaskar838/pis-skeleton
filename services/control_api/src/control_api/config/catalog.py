"""The settings catalog: every operator-owned value, declared once (ADR-0011).

A declaration says what a setting is (type, bounds, default, help) and who may change it. The *value* is set by
staff in the admin panel and stored in ``platform_setting``; until then the environment variable behind
``env_attr`` (a :class:`ControlSettings` attribute) or the default applies.

Each later phase adds its settings here, in the section of the car they belong to (Wheels for Floor 1, Fuel lines
for Floor 2, Engine bay for Floor 3, Trims & options for pricing).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from email.utils import parseaddr
from typing import Any, Final, Literal

SettingType = Literal["string", "int", "bool", "enum", "email", "url", "money", "secret"]
Section = Literal[
    "chassis", "body", "electricals", "trims", "wheels", "fuel_lines", "engine_bay", "switchgear", "locks"
]

SECTIONS: Final[dict[Section, tuple[str, str]]] = {
    "chassis": ("Chassis", "Platform structure: regions, launch countries and global limits"),
    "body": ("Body", "What customers see: product name, contacts and legal links"),
    "electricals": ("Electricals", "Integrations, e-mail delivery and API keys"),
    "trims": ("Trims & options", "Plans, add-ons and service prices"),
    "wheels": ("Wheels", "Floor 1: how data gets in"),
    "fuel_lines": ("Fuel lines", "Floor 2: how data is shaped"),
    "engine_bay": ("Engine bay", "Floor 3: tools and the engine socket"),
    "switchgear": ("Switchgear", "Feature flags and kill switches"),
    "locks": ("Locks & keys", "Staff access, audit and security"),
}

CURRENCIES: Final[frozenset[str]] = frozenset({"INR", "GBP", "EUR", "USD"})
_EMAIL = re.compile(r"^[^@\s<>]+@[^@\s<>]+\.[^@\s<>]+$")
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")
_MAX_MONEY = Decimal("1000000000")


class SettingValueError(ValueError):
    """The value does not fit the setting's declaration (shown to staff as a 422)."""


@dataclass(frozen=True)
class SettingDef:
    key: str
    section: Section
    label: str
    help: str
    type: SettingType
    default: Any = None
    env_attr: str | None = None
    min: int | None = None
    max: int | None = None
    choices: tuple[str, ...] = ()
    max_length: int = 200
    optional: bool = False
    public: bool = False
    used_from: str = "P0.5"

    @property
    def is_secret(self) -> bool:
        return self.type == "secret"

    @property
    def write_permission(self) -> str:
        return "platform:secrets:write" if self.is_secret else "platform:config:write"

    def validate(self, value: Any) -> Any:
        """Return the normalised value, or raise :class:`SettingValueError`."""
        check = getattr(self, f"_check_{self.type}")
        result: Any = check(value)
        return result

    # -- per-type checks
    def _text(self, value: Any, *, max_length: int | None = None) -> str:
        if not isinstance(value, str):
            raise SettingValueError("must be text")
        text = value.strip()
        if _CONTROL.search(text):
            raise SettingValueError("must not contain control characters")
        limit = max_length or self.max_length
        if len(text) > limit:
            raise SettingValueError(f"must be at most {limit} characters")
        if not text and not self.optional:
            raise SettingValueError("must not be empty")
        return text

    def _check_string(self, value: Any) -> str:
        return self._text(value)

    def _check_int(self, value: Any) -> int:
        if isinstance(value, bool) or not isinstance(value, int):
            raise SettingValueError("must be a whole number")
        if self.min is not None and value < self.min:
            raise SettingValueError(f"must be at least {self.min}")
        if self.max is not None and value > self.max:
            raise SettingValueError(f"must be at most {self.max}")
        return value

    def _check_bool(self, value: Any) -> bool:
        if not isinstance(value, bool):
            raise SettingValueError("must be true or false")
        return value

    def _check_enum(self, value: Any) -> str:
        if value not in self.choices:
            raise SettingValueError(f"must be one of: {', '.join(self.choices)}")
        return str(value)

    def _check_email(self, value: Any) -> str:
        text = self._text(value, max_length=254)
        if text and not _EMAIL.match(text):
            raise SettingValueError("must be an e-mail address")
        return text.lower()

    def _check_url(self, value: Any) -> str:
        text = self._text(value, max_length=500)
        if text and not (text.startswith("https://") or text.startswith("http://localhost")):
            raise SettingValueError("must start with https://")
        return text

    def _check_money(self, value: Any) -> dict[str, str]:
        if not isinstance(value, dict):
            raise SettingValueError("must be a map of currency to amount")
        out: dict[str, str] = {}
        for currency, amount in value.items():
            if currency not in CURRENCIES:
                raise SettingValueError(f"currency must be one of: {', '.join(sorted(CURRENCIES))}")
            if isinstance(amount, bool) or not isinstance(amount, str | int):
                raise SettingValueError('amounts must be numbers written as text, e.g. "499.00"')
            try:
                dec = Decimal(str(amount))
            except InvalidOperation:
                raise SettingValueError(f"{currency}: not a number") from None
            if not dec.is_finite() or dec < 0 or dec >= _MAX_MONEY or dec != dec.quantize(Decimal("0.01")):
                raise SettingValueError(
                    f"{currency}: must be between 0 and 999999999.99 with at most 2 decimals"
                )
            out[currency] = f"{dec:.2f}"
        return out

    def _check_secret(self, value: Any) -> str:
        if not isinstance(value, str) or not value or len(value) > 4096:
            raise SettingValueError("must be 1-4096 characters")
        return value


def _mail_from(text: str) -> str:
    _name, addr = parseaddr(text)
    if not _EMAIL.match(addr):
        raise SettingValueError('must look like "Name <address@example.com>"')
    return text


CATALOG: Final[tuple[SettingDef, ...]] = (
    # ---- Chassis: global limits
    SettingDef(
        "chassis.max_orgs_per_user",
        "chassis",
        "Organisations per user",
        "How many organisations one person may create.",
        "int",
        3,
        env_attr="max_orgs_per_user",
        min=1,
        max=100,
    ),
    SettingDef(
        "chassis.invite_ttl_days",
        "chassis",
        "Invitation lifetime (days)",
        "How long an invitation link stays valid.",
        "int",
        7,
        env_attr="invite_ttl_days",
        min=1,
        max=30,
    ),
    SettingDef(
        "chassis.deprovision_default_pending_days",
        "chassis",
        "Key deletion waiting period (days)",
        "Default waiting period before a deprovisioned tenant's key is destroyed (KMS allows 7-30).",
        "int",
        30,
        env_attr="deprovision_default_pending_days",
        min=7,
        max=30,
    ),
    # ---- Body: what customers see
    SettingDef(
        "body.product_name",
        "body",
        "Product name",
        "Shown in the apps, page titles and e-mails (F6).",
        "string",
        "DCS-PIS",
        max_length=60,
        public=True,
    ),
    SettingDef(
        "body.support_email",
        "body",
        "Support e-mail",
        "Where customers are told to write for help.",
        "email",
        "support@dcs-pis.local",
        public=True,
    ),
    SettingDef(
        "body.terms_url",
        "body",
        "Terms of service URL",
        "Linked from sign-up and the footer. Leave empty to hide.",
        "url",
        "",
        optional=True,
        public=True,
    ),
    SettingDef(
        "body.privacy_url",
        "body",
        "Privacy policy URL",
        "Linked from sign-up and the footer. Leave empty to hide.",
        "url",
        "",
        optional=True,
        public=True,
    ),
    # ---- Electricals: e-mail delivery
    SettingDef(
        "electricals.mail_from",
        "electricals",
        "E-mail sender",
        'Sender of every e-mail, as "Name <address>".',
        "string",
        "DCS-PIS <no-reply@dcs-pis.local>",
        env_attr="mail_from",
    ),
    SettingDef(
        "electricals.smtp_host",
        "electricals",
        "SMTP host",
        "Mail server (Amazon SES SMTP endpoint in production).",
        "string",
        "localhost",
        env_attr="smtp_host",
        max_length=253,
    ),
    SettingDef(
        "electricals.smtp_port",
        "electricals",
        "SMTP port",
        "Usually 587 (STARTTLS) in production.",
        "int",
        1025,
        env_attr="smtp_port",
        min=1,
        max=65535,
    ),
    SettingDef(
        "electricals.smtp_username",
        "electricals",
        "SMTP username",
        "Leave empty when the server needs no login.",
        "string",
        "",
        env_attr="smtp_user",
        optional=True,
    ),
    SettingDef(
        "electricals.smtp_password",
        "electricals",
        "SMTP password",
        "Write-only. Stored encrypted; nobody can read it back.",
        "secret",
        None,
        env_attr="smtp_password",
    ),
    SettingDef(
        "electricals.smtp_starttls",
        "electricals",
        "Use STARTTLS",
        "Encrypt the connection to the mail server. Required in production.",
        "bool",
        False,
        env_attr="smtp_tls",
    ),
    # ---- Trims & options: service prices
    SettingDef(
        "trims.concierge_onboarding",
        "trims",
        "Concierge onboarding",
        "Free at the start (F3). Switch to paid to charge the prices below.",
        "enum",
        "free",
        choices=("free", "paid"),
        used_from="P6",
    ),
    SettingDef(
        "trims.concierge_onboarding_price",
        "trims",
        "Concierge onboarding price",
        "One-off price per currency, used only when concierge onboarding is paid.",
        "money",
        {},
        used_from="P6",
    ),
    # ---- Fuel lines: LLM-assisted mapping (F2: a cheap, strong model on Amazon Bedrock)
    SettingDef(
        "fuel_lines.mapping_model",
        "fuel_lines",
        "Mapping model (Amazon Bedrock)",
        "Bedrock model or inference-profile ID that proposes field mappings. Default Claude Haiku 5.5: low cost, "
        "strong at classification. Switch to anthropic.claude-sonnet-5-5 if the mapping evaluation needs more.",
        "string",
        "anthropic.claude-haiku-5-5",
        max_length=200,
        used_from="P2",
    ),
    SettingDef(
        "fuel_lines.mapping_effort",
        "fuel_lines",
        "Mapping effort",
        "How hard the model thinks per request. Lower is cheaper and faster; raise it only if the evaluation shows "
        "better mappings.",
        "enum",
        "medium",
        choices=("low", "medium", "high"),
        used_from="P2",
    ),
)

SETTINGS_BY_KEY: Final[dict[str, SettingDef]] = {d.key: d for d in CATALOG}

# Extra checks that need more than the type (key → validator taking the type-checked value).
EXTRA_CHECKS: Final[dict[str, Any]] = {"electricals.mail_from": _mail_from}


def validate(key: str, value: Any) -> Any:
    definition = SETTINGS_BY_KEY[key]
    clean = definition.validate(value)
    extra = EXTRA_CHECKS.get(key)
    return extra(clean) if extra else clean


@dataclass(frozen=True)
class DeploymentValue:
    """A value the panel cannot change because the panel itself depends on it (ADR-0011 §3)."""

    label: str
    attr: str
    reveal: bool


DEPLOYMENT_OWNED: Final[tuple[DeploymentValue, ...]] = (
    DeploymentValue("Environment", "env", True),
    DeploymentValue("Control database URL", "control_db_url", False),
    DeploymentValue("Tenant cluster admin URL", "tenant_admin_url", False),
    DeploymentValue("Key service", "key_service", True),
    DeploymentValue("Local master key", "local_master_key", False),
    DeploymentValue("Customer identity issuer", "oidc_issuer", True),
    DeploymentValue("Staff identity issuer", "staff_oidc_issuer", True),
    DeploymentValue("Keycloak admin client secret", "keycloak_admin_client_secret", False),
    DeploymentValue("Redis", "redis_url", False),
    DeploymentValue("Temporal", "temporal_host", True),
    DeploymentValue("Object store endpoint", "s3_endpoint", True),
    DeploymentValue("Object store bucket", "s3_bucket", True),
    DeploymentValue("Object store credentials", "s3_secret_key", False),
    DeploymentValue("Customer web address", "web_base_url", True),
)
