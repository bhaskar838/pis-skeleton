from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr

from dcs_common.auth import IssuerConfig
from dcs_common.settings import DcsSettings


class ControlSettings(DcsSettings):
    service_name: str = "control-api"

    # --- databases
    # Full URLs (with passwords) come from the environment only; see .env.example.
    control_db_url: SecretStr = Field(
        default=SecretStr("postgresql+asyncpg://dcs_control_app@localhost:5432/dcs_control")
    )
    # Cluster admin used only by bootstrap and provisioning (CREATE DATABASE / ROLE / EXTENSION).
    tenant_admin_url: SecretStr = Field(default=SecretStr("postgresql://postgres@localhost:5432/postgres"))
    tenant_cluster: str = "local"
    tenant_db_host: str = "localhost"
    tenant_db_port: int = 5432

    # --- identity
    oidc_issuer: str = "http://keycloak.localhost:8080/realms/dcs"
    oidc_audience: str = "dcs-api"
    oidc_jwks_url: str | None = None
    staff_oidc_issuer: str = "http://keycloak.localhost:8080/realms/dcs-staff"
    staff_oidc_audience: str = "dcs-admin-api"
    staff_oidc_jwks_url: str | None = None
    mfa_enforce: bool = True
    require_verified_email: bool = True
    keycloak_admin_enabled: bool = False
    keycloak_base_url: str = "http://keycloak.localhost:8080"
    keycloak_realm: str = "dcs"
    keycloak_admin_client_id: str = "dcs-control-api"
    keycloak_admin_client_secret: SecretStr = SecretStr("")

    # --- keys
    key_service: Literal["local", "aws"] = "local"
    local_master_key: SecretStr = SecretStr("")
    local_key_dir: str = "./infra/local/keys"
    aws_region: str = "ap-south-1"

    # --- object store
    s3_endpoint: str | None = "http://localhost:9000"
    s3_bucket: str = "dcs-data-local"
    s3_access_key: SecretStr = SecretStr("")
    s3_secret_key: SecretStr = SecretStr("")
    s3_sse: Literal["none", "aws:kms"] = "none"
    object_lock_mode: Literal["none", "compliance"] = "none"

    # --- orchestration & messaging
    temporal_host: str = "localhost:7233"
    temporal_namespace: str = "default"
    temporal_task_queue: str = "control"
    redis_url: str = "redis://localhost:6379/0"

    # --- email
    smtp_host: str = "localhost"
    smtp_port: int = 1025
    smtp_user: str | None = None
    smtp_password: SecretStr | None = None
    smtp_tls: bool = False
    mail_from: str = "DCS-PIS <no-reply@dcs-pis.local>"
    web_base_url: str = "http://localhost:3000"

    # --- limits & policies
    max_orgs_per_user: int = 3
    invite_ttl_days: int = 7
    deprovision_default_pending_days: int = 30
    cors_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:3000", "http://localhost:3001"]
    )

    def issuers(self) -> list[IssuerConfig]:
        def jwks(issuer: str, override: str | None) -> str:
            return override or f"{issuer.rstrip('/')}/protocol/openid-connect/certs"

        return [
            IssuerConfig(
                "customer", self.oidc_issuer, self.oidc_audience, jwks(self.oidc_issuer, self.oidc_jwks_url)
            ),
            IssuerConfig(
                "staff",
                self.staff_oidc_issuer,
                self.staff_oidc_audience,
                jwks(self.staff_oidc_issuer, self.staff_oidc_jwks_url),
            ),
        ]


@lru_cache(maxsize=1)
def get_settings() -> ControlSettings:
    return ControlSettings()
