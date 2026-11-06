"""Workflow definitions. Activities are referenced by name, so this module stays sandbox-safe."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from temporalio import workflow
from temporalio.common import RetryPolicy
from temporalio.exceptions import ActivityError

with workflow.unsafe.imports_passed_through():
    from control_api.workflows.inputs import (
        AUDIT_VERIFY_WORKFLOW,
        DEPROVISION_WORKFLOW,
        PROVISION_WORKFLOW,
        AuditVerifyResult,
        DeprovisionInput,
        FailureInput,
        ProvisionInput,
        StepResult,
    )

RETRY = RetryPolicy(
    initial_interval=timedelta(seconds=2),
    backoff_coefficient=2.0,
    maximum_interval=timedelta(seconds=30),
    maximum_attempts=6,
    non_retryable_error_types=["ValueError"],
)


def _opts(minutes: int) -> dict[str, Any]:
    return {"start_to_close_timeout": timedelta(minutes=minutes), "retry_policy": RETRY}


PROVISION_STEPS: tuple[tuple[str, int], ...] = (
    ("provision.create_idp_group", 2),
    ("provision.create_tenant_key", 2),
    ("provision.create_tenant_database", 3),
    ("provision.run_tenant_migrations", 5),
    ("provision.create_object_prefixes", 2),
    ("provision.finalize", 2),
)

DEPROVISION_STEPS: tuple[tuple[str, int], ...] = (
    ("deprovision.delete_idp_group", 2),
    ("deprovision.drop_database", 5),
    ("deprovision.delete_object_prefixes", 10),
    ("deprovision.schedule_key_deletion", 2),
    ("deprovision.finalize", 2),
)


@workflow.defn(name=PROVISION_WORKFLOW)
class ProvisionTenantWorkflow:
    def __init__(self) -> None:
        self.done: list[str] = []

    @workflow.query
    def progress(self) -> list[str]:
        return self.done

    @workflow.run
    async def run(self, inp: ProvisionInput) -> list[str]:
        try:
            for name, minutes in PROVISION_STEPS:
                result = await workflow.execute_activity(name, inp, result_type=StepResult, **_opts(minutes))
                self.done.append(result.step)
        except ActivityError as err:
            cause = err.cause or err
            await workflow.execute_activity(
                "provision.mark_failed",
                FailureInput(inp.org_id, inp.tenant_id, str(cause)),
                result_type=StepResult,
                **_opts(1),
            )
            raise
        return self.done


@workflow.defn(name=DEPROVISION_WORKFLOW)
class DeprovisionTenantWorkflow:
    def __init__(self) -> None:
        self.done: list[str] = []

    @workflow.query
    def progress(self) -> list[str]:
        return self.done

    @workflow.run
    async def run(self, inp: DeprovisionInput) -> list[str]:
        for name, minutes in DEPROVISION_STEPS:
            result = await workflow.execute_activity(name, inp, result_type=StepResult, **_opts(minutes))
            self.done.append(result.step)
        return self.done


@workflow.defn(name=AUDIT_VERIFY_WORKFLOW)
class AuditVerifyWorkflow:
    @workflow.run
    async def run(self, _: None = None) -> AuditVerifyResult:
        result: AuditVerifyResult = await workflow.execute_activity(
            "audit.verify_all", result_type=AuditVerifyResult, **_opts(30)
        )
        return result


WORKFLOWS = [ProvisionTenantWorkflow, DeprovisionTenantWorkflow, AuditVerifyWorkflow]
