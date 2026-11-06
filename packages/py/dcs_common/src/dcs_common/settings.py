"""Base settings shared by every service (pydantic-settings, env prefix ``DCS_``)."""

from __future__ import annotations

from typing import Literal, Self

from pydantic import AliasChoices, Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

Environment = Literal["local", "ci", "staging", "prod"]


class OidcIssuerSettings(BaseSettings):
    """One trusted OIDC issuer (a Keycloak realm)."""

    model_config = SettingsConfigDict(extra="ignore")

    issuer: str
    audience: str = "dcs-api"
    jwks_url: str | None = None

    def resolved_jwks_url(self) -> str:
        # Keycloak's well-known JWKS path; overridable for other IdPs.
        return self.jwks_url or f"{self.issuer.rstrip('/')}/protocol/openid-connect/certs"


class DcsSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="DCS_", extra="ignore", env_nested_delimiter="__")

    env: Environment = "local"
    service_name: str = "dcs"
    log_level: str = "INFO"
    otel_endpoint: str | None = Field(
        default=None, validation_alias=AliasChoices("OTEL_EXPORTER_OTLP_ENDPOINT", "DCS_OTEL_ENDPOINT")
    )
    sentry_dsn: SecretStr | None = Field(
        default=None, validation_alias=AliasChoices("SENTRY_DSN", "DCS_SENTRY_DSN")
    )
    # MFA for Owner/Admin/staff (SPEC §8.3, OPEN_QUESTIONS Q5). May be switched off for local/CI only.
    mfa_enforce: bool = True

    @property
    def is_production_like(self) -> bool:
        return self.env in ("staging", "prod")

    @model_validator(mode="after")
    def _mfa_cannot_be_disabled_outside_dev(self) -> Self:
        if self.is_production_like and not self.mfa_enforce:
            raise ValueError(f"DCS_MFA_ENFORCE=false is not allowed when DCS_ENV={self.env}")
        return self
