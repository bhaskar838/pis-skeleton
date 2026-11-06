"""Provisioning, deprovisioning and audit-verification activities (SPEC §8.1, §8.5).

Every activity is idempotent (safe to retry) and writes an audit event to the tenant's chain, so the audit trail
shows every step (Phase 0 acceptance criterion).
"""

from __future__ import annotations

import contextlib
import logging
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import delete, select, update
from sqlalchemy.dialects.postgresql import insert
from temporalio import activity

from control_api import audit
from control_api.audit import Actor
from control_api.db import Database
from control_api.infra import tenant_db
from control_api.infra.keycloak import IdpAdmin
from control_api.infra.objectstore import TenantObjectStore
from control_api.mailer import Mailer
from control_api.models import Credential, Invite, Membership, Org, TenantDb, TenantKey
from control_api.notifications import notify
from control_api.realtime import Publisher, org_channel
from control_api.settings import ControlSettings
from control_api.workflows.inputs import (
    AuditVerifyResult,
    DeprovisionInput,
    FailureInput,
    ProvisionInput,
    StepResult,
)
from dcs_cbm import CBM_VERSION
from dcs_common import context
from dcs_vault import Sealed, Vault, build_aad
from dcs_vault import TenantKey as VaultTenantKey

log = logging.getLogger(__name__)
SYSTEM = Actor.system("control-worker")
DB_ROLE_KINDS = ("owner", "rw", "ro")


def credential_kind(role_kind: str) -> str:
    return f"tenant_db_role:{role_kind}"


@dataclass
class ProvisioningActivities:
    settings: ControlSettings
    db: Database
    vault: Vault
    store: TenantObjectStore
    idp: IdpAdmin
    publisher: Publisher
    mailer: Mailer

    # ----------------------------------------------------------------------------------- helpers
    def _bind(self, tenant_id: str) -> None:
        context.tenant_id_var.set(tenant_id)
        with contextlib.suppress(RuntimeError):  # outside an activity (tests)
            context.workflow_id_var.set(activity.info().workflow_id)

    async def _step(
        self, org_id: str, tenant_id: str, action: str, details: dict[str, Any] | None = None
    ) -> None:
        async with self.db.platform_tx() as s:
            await audit.emit(
                s,
                actor=SYSTEM,
                action=action,
                org_id=uuid.UUID(org_id),
                target_type="tenant",
                target_id=tenant_id,
                details=details or {},
            )
        await self.publisher.publish(
            org_channel(tenant_id), {"type": "provisioning.step", "action": action, "details": details or {}}
        )

    async def _tenant_key(self, org_id: str, tenant_id: str) -> VaultTenantKey:
        async with self.db.platform_tx() as s:
            row = await s.get(TenantKey, uuid.UUID(org_id))
        if row is None:
            raise RuntimeError("tenant key missing; create_tenant_key must run first")
        return VaultTenantKey(tenant_id, row.kms_key_arn, bytes(row.wrapped_dek))

    async def role_password(self, org_id: str, tenant_id: str, kind: str, *, create: bool = False) -> str:
        """Return the tenant DB role password, generating and sealing it on first use."""
        tkey = await self._tenant_key(org_id, tenant_id)
        cred_kind = credential_kind(kind)
        async with self.db.platform_tx() as s:
            cred = await s.scalar(
                select(Credential).where(
                    Credential.org_id == uuid.UUID(org_id),
                    Credential.kind == cred_kind,
                    Credential.source_id.is_(None),
                )
            )
            if cred is not None:
                sealed = Sealed(bytes(cred.ciphertext), bytes(cred.nonce), cred.aad)
                return (await self.vault.open(tkey, sealed)).decode()
            if not create:
                raise RuntimeError(f"credential {cred_kind} missing")
            password = secrets.token_urlsafe(32)
            sealed = await self.vault.seal(
                tkey, password.encode(), build_aad(tenant_id, "tenant_db_role", kind)
            )
            stmt = (
                insert(Credential)
                .values(
                    org_id=uuid.UUID(org_id),
                    kind=cred_kind,
                    ciphertext=sealed.ciphertext,
                    nonce=sealed.nonce,
                    aad=sealed.aad,
                )
                .on_conflict_do_nothing()
            )
            await s.execute(stmt)
        # Re-read so a concurrent attempt that won the insert race decides the password.
        return await self.role_password(org_id, tenant_id, kind)

    # ------------------------------------------------------------------------------- provisioning
    @activity.defn(name="provision.create_idp_group")
    async def create_idp_group(self, inp: ProvisionInput) -> StepResult:
        self._bind(inp.tenant_id)
        group = await self.idp.ensure_group(inp.tenant_id, inp.org_id)
        await self._step(inp.org_id, inp.tenant_id, "tenant.provision.idp_group_created", {"group": group})
        return StepResult("idp_group", group)

    @activity.defn(name="provision.create_tenant_key")
    async def create_tenant_key(self, inp: ProvisionInput) -> StepResult:
        self._bind(inp.tenant_id)
        org_uuid = uuid.UUID(inp.org_id)
        async with self.db.platform_tx() as s:
            if await s.get(TenantKey, org_uuid) is not None:
                return StepResult("tenant_key", "exists")
        tkey = await self.vault.new_tenant_key(inp.tenant_id)
        async with self.db.platform_tx() as s:
            await s.execute(
                insert(TenantKey)
                .values(
                    org_id=org_uuid,
                    kms_key_arn=tkey.key_ref,
                    wrapped_dek=tkey.wrapped_dek,
                    status="active",
                )
                .on_conflict_do_nothing()
            )
        await self._step(
            inp.org_id,
            inp.tenant_id,
            "tenant.provision.key_created",
            {"provider": "aws-kms" if tkey.key_ref.startswith("arn:") else "local"},
        )
        return StepResult("tenant_key", "created")

    @activity.defn(name="provision.create_tenant_database")
    async def create_tenant_database(self, inp: ProvisionInput) -> StepResult:
        self._bind(inp.tenant_id)
        passwords = {
            k: await self.role_password(inp.org_id, inp.tenant_id, k, create=True) for k in DB_ROLE_KINDS
        }
        extensions = await tenant_db.create_database(
            self.settings.tenant_admin_url.get_secret_value(), inp.tenant_id, passwords
        )
        roles = [tenant_db.role_name(inp.tenant_id, k) for k in ("owner", "rw", "ro", "engine_ro")]
        await self._step(
            inp.org_id,
            inp.tenant_id,
            "tenant.provision.database_created",
            {"database": inp.tenant_id, "roles": roles, "extensions": extensions},
        )
        return StepResult("database", inp.tenant_id)

    @activity.defn(name="provision.run_tenant_migrations")
    async def run_tenant_migrations(self, inp: ProvisionInput) -> StepResult:
        self._bind(inp.tenant_id)
        owner_pw = await self.role_password(inp.org_id, inp.tenant_id, "owner")
        await tenant_db.run_migrations(
            self.settings.tenant_db_host, self.settings.tenant_db_port, inp.tenant_id, owner_pw
        )
        async with self.db.platform_tx() as s:
            await s.execute(
                update(TenantDb)
                .where(TenantDb.org_id == uuid.UUID(inp.org_id))
                .values(cbm_version=CBM_VERSION, updated_at=datetime.now(UTC))
            )
        await self._step(inp.org_id, inp.tenant_id, "tenant.provision.migrated", {"cbm_version": CBM_VERSION})
        return StepResult("migrations", CBM_VERSION)

    @activity.defn(name="provision.create_object_prefixes")
    async def create_object_prefixes(self, inp: ProvisionInput) -> StepResult:
        self._bind(inp.tenant_id)
        tkey = await self._tenant_key(inp.org_id, inp.tenant_id)
        keys = await self.store.create_prefixes(
            inp.tenant_id, tkey.key_ref if tkey.key_ref.startswith("arn:") else None
        )
        await self._step(
            inp.org_id,
            inp.tenant_id,
            "tenant.provision.prefixes_created",
            {"prefixes": [k.rsplit("/", 2)[-2] for k in keys], "sse": self.settings.s3_sse},
        )
        return StepResult("prefixes", str(len(keys)))

    @activity.defn(name="provision.finalize")
    async def finalize(self, inp: ProvisionInput) -> StepResult:
        self._bind(inp.tenant_id)
        org_uuid = uuid.UUID(inp.org_id)
        async with self.db.platform_tx() as s:
            org = await s.get(Org, org_uuid, with_for_update=True)
            if org is None:
                raise RuntimeError("org disappeared during provisioning")
            if org.status == "active":
                return StepResult("finalize", "already active")
            org.status = "active"
            await s.execute(
                update(TenantDb)
                .where(TenantDb.org_id == org_uuid)
                .values(status="ready", updated_at=datetime.now(UTC))
            )
            await audit.emit(
                s,
                actor=SYSTEM,
                action="tenant.provisioned",
                org_id=org_uuid,
                target_type="tenant",
                target_id=inp.tenant_id,
            )
            owners = list(
                (
                    await s.scalars(
                        select(Membership.user_id).where(
                            Membership.org_id == org_uuid,
                            Membership.role == "owner",
                            Membership.status == "active",
                        )
                    )
                ).all()
            )
            await notify(
                s,
                self.publisher,
                self.mailer,
                org_id=org_uuid,
                user_ids=owners,
                event_type="tenant.provisioned",
                payload={"message": f"{org.name} is ready to use.", "tenant_id": inp.tenant_id},
                link=self.settings.web_base_url,
            )
        await self.publisher.publish(org_channel(inp.tenant_id), {"type": "tenant.provisioned"})
        return StepResult("finalize", "active")

    @activity.defn(name="provision.mark_failed")
    async def mark_failed(self, inp: FailureInput) -> StepResult:
        self._bind(inp.tenant_id)
        org_uuid = uuid.UUID(inp.org_id)
        async with self.db.platform_tx() as s:
            await s.execute(
                update(Org).where(Org.id == org_uuid, Org.status == "provisioning").values(status="failed")
            )
            await s.execute(update(TenantDb).where(TenantDb.org_id == org_uuid).values(status="failed"))
            await audit.emit(
                s,
                actor=SYSTEM,
                action="tenant.provision.failed",
                org_id=org_uuid,
                target_type="tenant",
                target_id=inp.tenant_id,
                details={"error": inp.error[:500]},
            )
        await self.publisher.publish(org_channel(inp.tenant_id), {"type": "provisioning.failed"})
        return StepResult("failed", inp.error[:200])

    # ----------------------------------------------------------------------------- deprovisioning
    @activity.defn(name="deprovision.delete_idp_group")
    async def delete_idp_group(self, inp: DeprovisionInput) -> StepResult:
        self._bind(inp.tenant_id)
        deleted = await self.idp.delete_group(inp.tenant_id)
        await self._step(
            inp.org_id, inp.tenant_id, "tenant.deprovision.idp_group_deleted", {"deleted": deleted}
        )
        return StepResult("idp_group", str(deleted))

    @activity.defn(name="deprovision.drop_database")
    async def drop_database(self, inp: DeprovisionInput) -> StepResult:
        self._bind(inp.tenant_id)
        await tenant_db.drop_database(self.settings.tenant_admin_url.get_secret_value(), inp.tenant_id)
        async with self.db.platform_tx() as s:
            await s.execute(
                update(TenantDb)
                .where(TenantDb.org_id == uuid.UUID(inp.org_id))
                .values(status="dropped", updated_at=datetime.now(UTC))
            )
        await self._step(
            inp.org_id, inp.tenant_id, "tenant.deprovision.database_dropped", {"database": inp.tenant_id}
        )
        return StepResult("database", "dropped")

    @activity.defn(name="deprovision.delete_object_prefixes")
    async def delete_object_prefixes(self, inp: DeprovisionInput) -> StepResult:
        self._bind(inp.tenant_id)
        count, mode = await self.store.delete_prefix(inp.tenant_id)
        await self._step(
            inp.org_id, inp.tenant_id, "tenant.deprovision.prefixes_deleted", {"objects": count, "mode": mode}
        )
        return StepResult("prefixes", mode)

    @activity.defn(name="deprovision.schedule_key_deletion")
    async def schedule_key_deletion(self, inp: DeprovisionInput) -> StepResult:
        self._bind(inp.tenant_id)
        org_uuid = uuid.UUID(inp.org_id)
        async with self.db.platform_tx() as s:
            row = await s.get(TenantKey, org_uuid)
        if row is None:
            return StepResult("key", "absent")
        when = await self.vault.key_service.schedule_key_deletion(row.kms_key_arn, inp.pending_days)
        self.vault.forget(inp.tenant_id)
        async with self.db.platform_tx() as s:
            await s.execute(
                update(TenantKey)
                .where(TenantKey.org_id == org_uuid)
                .values(status="pending_deletion", deletion_scheduled_at=when)
            )
        await self._step(
            inp.org_id,
            inp.tenant_id,
            "tenant.deprovision.key_deletion_scheduled",
            {"deletion_date": when.isoformat(), "pending_days": inp.pending_days},
        )
        return StepResult("key", when.isoformat())

    @activity.defn(name="deprovision.finalize")
    async def finalize_deprovision(self, inp: DeprovisionInput) -> StepResult:
        self._bind(inp.tenant_id)
        org_uuid = uuid.UUID(inp.org_id)
        async with self.db.platform_tx() as s:
            await s.execute(delete(Credential).where(Credential.org_id == org_uuid))
            await s.execute(
                update(Invite)
                .where(Invite.org_id == org_uuid, Invite.status == "pending")
                .values(status="revoked")
            )
            await s.execute(
                update(Membership)
                .where(Membership.org_id == org_uuid, Membership.status == "active")
                .values(status="removed", updated_at=datetime.now(UTC))
            )
            await s.execute(update(Org).where(Org.id == org_uuid).values(status="deleted"))
            await audit.emit(
                s,
                actor=SYSTEM,
                action="tenant.deprovisioned",
                org_id=org_uuid,
                target_type="tenant",
                target_id=inp.tenant_id,
                details={"reason": inp.reason, "requested_by": inp.requested_by},
            )
        return StepResult("finalize", "deleted")

    # ------------------------------------------------------------------------------ audit verify
    @activity.defn(name="audit.verify_all")
    async def verify_all_chains(self) -> AuditVerifyResult:
        async with self.db.platform_tx() as s:
            chain_ids = await audit.chains(s)
        failing = 0
        for chain in chain_ids:
            async with self.db.platform_tx() as s:
                result = await audit.verify_org_chain(s, chain)
            if not result.ok:
                failing += 1
                log.error(
                    "audit chain verification FAILED",
                    extra={"chain": str(chain), "first_bad_id": result.first_bad_id, "reason": result.reason},
                )
                async with self.db.platform_tx() as s:
                    await audit.emit(
                        s,
                        actor=SYSTEM,
                        action="audit.chain.verification_failed",
                        org_id=None,
                        target_type="audit_chain",
                        target_id=str(chain),
                        details={"first_bad_id": result.first_bad_id, "reason": result.reason},
                    )
        return AuditVerifyResult(chains=len(chain_ids), failing=failing)

    def all(self) -> list[Any]:
        return [
            self.create_idp_group,
            self.create_tenant_key,
            self.create_tenant_database,
            self.run_tenant_migrations,
            self.create_object_prefixes,
            self.finalize,
            self.mark_failed,
            self.delete_idp_group,
            self.drop_database,
            self.delete_object_prefixes,
            self.schedule_key_deletion,
            self.finalize_deprovision,
            self.verify_all_chains,
        ]
