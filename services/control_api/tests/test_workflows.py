"""Workflow definitions on a real Temporal test server (time-skipping), with stub activities.

Checks step order, that a failing step triggers ``provision.mark_failed``, and the deprovision sequence.
"""

from __future__ import annotations

import uuid

import pytest
from temporalio import activity
from temporalio.client import WorkflowFailureError
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from control_api.workflows.definitions import DEPROVISION_STEPS, PROVISION_STEPS, WORKFLOWS
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

pytestmark = pytest.mark.integration


def stub_activities(calls: list[str], fail_on: str | None = None) -> list[object]:
    def make(name: str) -> object:
        @activity.defn(name=name)
        async def _act(inp: ProvisionInput | DeprovisionInput) -> StepResult:
            calls.append(name)
            if name == fail_on:
                raise ValueError(f"{name} exploded")  # ValueError is non-retryable in RETRY
            return StepResult(name.split(".", 1)[1])

        return _act

    @activity.defn(name="provision.mark_failed")
    async def mark_failed(inp: FailureInput) -> StepResult:
        calls.append(f"mark_failed:{inp.tenant_id}")
        return StepResult("failed")

    @activity.defn(name="audit.verify_all")
    async def verify_all() -> AuditVerifyResult:
        calls.append("audit.verify_all")
        return AuditVerifyResult(chains=3, failing=0)

    names = [n for n, _ in PROVISION_STEPS] + [n for n, _ in DEPROVISION_STEPS]
    return [make(n) for n in names] + [mark_failed, verify_all]


@pytest.fixture(scope="module")
async def env() -> WorkflowEnvironment:
    environment = await WorkflowEnvironment.start_time_skipping()
    yield environment  # type: ignore[misc]
    await environment.shutdown()


async def _run(
    env: WorkflowEnvironment, calls: list[str], workflow: str, arg: object, fail_on: str | None = None
):  # type: ignore[no-untyped-def]
    queue = f"q-{uuid.uuid4().hex[:8]}"
    async with Worker(
        env.client, task_queue=queue, workflows=WORKFLOWS, activities=stub_activities(calls, fail_on)
    ):
        return await env.client.execute_workflow(workflow, arg, id=f"wf-{uuid.uuid4().hex}", task_queue=queue)


async def test_provision_runs_steps_in_order(env: WorkflowEnvironment) -> None:
    calls: list[str] = []
    result = await _run(env, calls, PROVISION_WORKFLOW, ProvisionInput("o", "t_abcdefghij", "u"))
    assert calls == [n for n, _ in PROVISION_STEPS]
    assert result == [
        "create_idp_group",
        "create_tenant_key",
        "create_tenant_database",
        "run_tenant_migrations",
        "create_object_prefixes",
        "finalize",
    ]


async def test_provision_failure_marks_failed(env: WorkflowEnvironment) -> None:
    calls: list[str] = []
    with pytest.raises(WorkflowFailureError):
        await _run(
            env,
            calls,
            PROVISION_WORKFLOW,
            ProvisionInput("o", "t_abcdefghij", "u"),
            fail_on="provision.create_tenant_database",
        )
    assert calls == [
        "provision.create_idp_group",
        "provision.create_tenant_key",
        "provision.create_tenant_database",
        "mark_failed:t_abcdefghij",
    ]


async def test_deprovision_sequence(env: WorkflowEnvironment) -> None:
    calls: list[str] = []
    await _run(env, calls, DEPROVISION_WORKFLOW, DeprovisionInput("o", "t_abcdefghij", "staff", "test", 7))
    assert calls == [n for n, _ in DEPROVISION_STEPS]


async def test_audit_verify_workflow(env: WorkflowEnvironment) -> None:
    calls: list[str] = []
    result = await _run(env, calls, AUDIT_VERIFY_WORKFLOW, None)
    assert calls == ["audit.verify_all"]
    assert result == {"chains": 3, "failing": 0}  # untyped start by name returns the JSON payload
