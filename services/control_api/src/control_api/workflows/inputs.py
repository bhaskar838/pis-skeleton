"""Workflow / activity payloads. Plain dataclasses: safe to import inside the Temporal workflow sandbox."""

from __future__ import annotations

from dataclasses import dataclass

PROVISION_WORKFLOW = "ProvisionTenantWorkflow"
DEPROVISION_WORKFLOW = "DeprovisionTenantWorkflow"
AUDIT_VERIFY_WORKFLOW = "AuditVerifyWorkflow"
AUDIT_VERIFY_SCHEDULE_ID = "audit-verify-nightly"


@dataclass(frozen=True)
class ProvisionInput:
    org_id: str
    tenant_id: str
    requested_by: str  # actor id (user uuid)


@dataclass(frozen=True)
class DeprovisionInput:
    org_id: str
    tenant_id: str
    requested_by: str  # staff subject
    reason: str
    pending_days: int = 30


@dataclass(frozen=True)
class FailureInput:
    org_id: str
    tenant_id: str
    error: str


@dataclass(frozen=True)
class StepResult:
    step: str
    detail: str = ""


@dataclass(frozen=True)
class AuditVerifyResult:
    chains: int
    failing: int
