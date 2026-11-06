"""Test toolkit shared by control-api, data-api and the isolation suite. Never imported by production code."""

from __future__ import annotations

import asyncio
import os
import secrets
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa

from control_api.bootstrap import CONTROL_DB, ensure_roles_and_db, migrate
from control_api.db import Database
from control_api.infra.keycloak import NoopIdpAdmin
from control_api.infra.objectstore import ObjectStoreConfig, TenantObjectStore
from control_api.mailer import MemoryMailer
from control_api.realtime import MemoryPublisher
from control_api.settings import ControlSettings
from control_api.state import AppState
from control_api.workflows.activities import ProvisioningActivities
from control_api.workflows.definitions import DEPROVISION_STEPS, PROVISION_STEPS
from control_api.workflows.inputs import (
    AUDIT_VERIFY_WORKFLOW,
    DEPROVISION_WORKFLOW,
    PROVISION_WORKFLOW,
    FailureInput,
)
from dcs_common.auth import IssuerConfig, JwksCache, TokenValidator, static_jwks_fetcher
from dcs_vault import LocalKeyService, Vault

CUSTOMER_ISSUER = "http://kc.test/realms/dcs"
STAFF_ISSUER = "http://kc.test/realms/dcs-staff"


class TokenFactory:
    def __init__(self) -> None:
        self._key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        jwk = jwt.algorithms.RSAAlgorithm.to_jwk(self._key.public_key(), as_dict=True)
        jwk.update({"kid": "test", "use": "sig", "alg": "RS256"})
        self.jwks = {"keys": [jwk]}

    def validator(self) -> TokenValidator:
        return TokenValidator(
            [
                IssuerConfig("customer", CUSTOMER_ISSUER, "dcs-api", "jwks://customer"),
                IssuerConfig("staff", STAFF_ISSUER, "dcs-admin-api", "jwks://staff"),
            ],
            JwksCache(static_jwks_fetcher(self.jwks)),
        )

    def customer(
        self, sub: str, email: str, *, mfa: bool = False, verified: bool = True, name: str | None = None
    ) -> str:
        return self._issue(
            CUSTOMER_ISSUER,
            "dcs-api",
            sub,
            email=email,
            email_verified=verified,
            name=name or email.split("@")[0],
            acr="mfa" if mfa else "1",
        )

    def staff(self, sub: str, roles: list[str], *, mfa: bool = True) -> str:
        return self._issue(
            STAFF_ISSUER,
            "dcs-admin-api",
            sub,
            email=f"{sub}@dcs.example",
            realm_access={"roles": roles},
            acr="mfa" if mfa else "1",
        )

    def _issue(self, iss: str, aud: str, sub: str, **claims: Any) -> str:
        now = int(time.time())
        body = {"iss": iss, "aud": aud, "sub": sub, "iat": now, "exp": now + 600, **claims}
        return jwt.encode(body, self._key, algorithm="RS256", headers={"kid": "test"})


@dataclass(frozen=True)
class ClusterUrls:
    admin_url: str  # postgresql://postgres:pw@host:port/postgres
    host: str
    port: int
    passwords: dict[str, str]

    def control(self, role: str, driver: str = "asyncpg") -> str:
        return f"postgresql+{driver}://{role}:{self.passwords[role]}@{self.host}:{self.port}/{CONTROL_DB}"


async def bootstrap_cluster(admin_url: str, host: str, port: int) -> ClusterUrls:
    passwords = {
        r: secrets.token_urlsafe(16) for r in ("dcs_control_owner", "dcs_control_app", "dcs_control_reader")
    }
    await ensure_roles_and_db(admin_url, passwords)
    await asyncio.to_thread(migrate, admin_url, passwords["dcs_control_owner"])
    return ClusterUrls(admin_url, host, port, passwords)


def make_settings(urls: ClusterUrls, key_dir: Path, **overrides: Any) -> ControlSettings:
    master = os.urandom(32)
    import base64

    values: dict[str, Any] = {
        "env": "ci",
        "control_db_url": urls.control("dcs_control_app"),
        "tenant_admin_url": urls.admin_url,
        "tenant_db_host": urls.host,
        "tenant_db_port": urls.port,
        "oidc_issuer": CUSTOMER_ISSUER,
        "staff_oidc_issuer": STAFF_ISSUER,
        "key_service": "local",
        "local_master_key": base64.b64encode(master).decode(),
        "local_key_dir": str(key_dir),
        "s3_bucket": "dcs-test",
        "s3_endpoint": None,
        "web_base_url": "http://web.test",
    }
    values.update(overrides)
    return ControlSettings(**values)


@dataclass
class InlineWorkflows:
    """Stands in for Temporal: runs the workflow's activities in-process, in the same order as the definitions."""

    activities: ProvisioningActivities | None = None
    started: list[tuple[str, Any, str]] = field(default_factory=list)
    run_inline: bool = True

    async def start(
        self, workflow: str, arg: object, *, workflow_id: str, allow_retry_failed: bool = False
    ) -> str:
        self.started.append((workflow, arg, workflow_id))
        if not self.run_inline or self.activities is None:
            return workflow_id
        acts = self.activities
        by_name = {getattr(fn, "__temporal_activity_definition").name: fn for fn in acts.all()}
        if workflow == PROVISION_WORKFLOW:
            try:
                for name, _ in PROVISION_STEPS:
                    await by_name[name](arg)
            except Exception as exc:
                await acts.mark_failed(FailureInput(arg.org_id, arg.tenant_id, str(exc)))  # type: ignore[attr-defined]
                raise
        elif workflow == DEPROVISION_WORKFLOW:
            for name, _ in DEPROVISION_STEPS:
                await by_name[name](arg)
        elif workflow == AUDIT_VERIFY_WORKFLOW:
            await acts.verify_all_chains()
        return workflow_id


def build_test_state(settings: ControlSettings, tokens: TokenFactory, store: TenantObjectStore) -> AppState:
    import base64

    db = Database(settings.control_db_url.get_secret_value(), pool_size=5)
    publisher = MemoryPublisher()
    mailer = MemoryMailer()
    vault = Vault(
        LocalKeyService(
            base64.b64decode(settings.local_master_key.get_secret_value()), Path(settings.local_key_dir)
        )
    )
    acts = ProvisioningActivities(
        settings=settings,
        db=Database(settings.control_db_url.get_secret_value(), pool_size=3),
        vault=vault,
        store=store,
        idp=NoopIdpAdmin(),
        publisher=publisher,
        mailer=mailer,
    )
    return AppState(
        settings=settings,
        db=db,
        validator=tokens.validator(),
        workflows=InlineWorkflows(acts),  # type: ignore[arg-type]
        publisher=publisher,
        mailer=mailer,
        vault=vault,
    )


def new_store(client: Any, bucket: str) -> TenantObjectStore:
    return TenantObjectStore(client, ObjectStoreConfig(bucket))


def unique_email(prefix: str = "user") -> str:
    return f"{prefix}.{uuid.uuid4().hex[:10]}@example.test"
