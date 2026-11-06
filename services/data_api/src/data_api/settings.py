from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr

from dcs_common.auth import IssuerConfig
from dcs_common.settings import DcsSettings


class DataSettings(DcsSettings):
    service_name: str = "data-api"
    # Connects as dcs_control_reader: SELECT on a few control tables, tenant `_ro` credentials only.
    control_reader_url: SecretStr = Field(
        default=SecretStr("postgresql+asyncpg://dcs_control_reader@localhost:5432/dcs_control")
    )
    tenant_db_host: str = "localhost"
    tenant_db_port: int = 5432
    tenant_pool_size: int = 5
    max_tenant_pools: int = 200

    oidc_issuer: str = "http://keycloak.localhost:8080/realms/dcs"
    oidc_audience: str = "dcs-api"
    oidc_jwks_url: str | None = None
    mfa_enforce: bool = True

    key_service: Literal["local", "aws"] = "local"
    local_master_key: SecretStr = SecretStr("")
    local_key_dir: str = "./infra/local/keys"
    aws_region: str = "ap-south-1"
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3000"])

    def issuers(self) -> list[IssuerConfig]:
        jwks = self.oidc_jwks_url or f"{self.oidc_issuer.rstrip('/')}/protocol/openid-connect/certs"
        return [IssuerConfig("customer", self.oidc_issuer, self.oidc_audience, jwks)]


@lru_cache(maxsize=1)
def get_settings() -> DataSettings:
    return DataSettings()
