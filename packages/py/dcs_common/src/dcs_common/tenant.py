"""TenantContext: the only way data-plane code learns which tenant it serves (SPEC §8.2)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from dcs_common.ids import is_tenant_id


class TenantGuardError(RuntimeError):
    """Raised when a connection is about to be used against the wrong tenant database."""


@dataclass(frozen=True)
class TenantContext:
    org_id: uuid.UUID
    tenant_id: str

    def __post_init__(self) -> None:
        if not is_tenant_id(self.tenant_id):
            raise ValueError(f"invalid tenant id: {self.tenant_id!r}")

    @property
    def db_name(self) -> str:
        return self.tenant_id

    @property
    def redis_prefix(self) -> str:
        return f"t:{self.tenant_id}:"

    def role(self, kind: str) -> str:
        if kind not in ("owner", "rw", "ro", "engine_ro"):
            raise ValueError(f"unknown tenant role kind: {kind}")
        return f"{self.tenant_id}_{kind}"

    def object_prefix(self, zone: str | None = None) -> str:
        base = f"tenants/{self.tenant_id}/"
        if zone is None:
            return base
        if zone not in ("landing", "bronze", "exports", "browser-artifacts"):
            raise ValueError(f"unknown zone: {zone}")
        return f"{base}{zone}/"

    def assert_database(self, actual_db_name: str | None) -> None:
        if actual_db_name != self.db_name:
            raise TenantGuardError(
                f"tenant guard: connection is on database {actual_db_name!r}, expected {self.db_name!r}"
            )
