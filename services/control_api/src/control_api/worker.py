"""control-worker: runs provisioning + audit workflows on task queue ``control``."""

from __future__ import annotations

import asyncio
import logging

from temporalio.client import Client, Schedule, ScheduleActionStartWorkflow, ScheduleSpec
from temporalio.contrib.opentelemetry import TracingInterceptor
from temporalio.service import RPCError
from temporalio.worker import Worker

from control_api.db import Database
from control_api.infra.keycloak import IdpAdmin, KeycloakAdmin, NoopIdpAdmin
from control_api.infra.objectstore import ObjectStoreConfig, TenantObjectStore, build_client
from control_api.mailer import SmtpMailer
from control_api.realtime import RedisPublisher
from control_api.settings import ControlSettings, get_settings
from control_api.state import build_key_service
from control_api.temporal import connect
from control_api.workflows.activities import ProvisioningActivities
from control_api.workflows.definitions import WORKFLOWS
from control_api.workflows.inputs import AUDIT_VERIFY_SCHEDULE_ID, AUDIT_VERIFY_WORKFLOW
from dcs_common.logging import configure_logging
from dcs_common.telemetry import setup_telemetry
from dcs_vault import Vault

log = logging.getLogger(__name__)


def build_activities(settings: ControlSettings) -> ProvisioningActivities:
    idp: IdpAdmin = (
        KeycloakAdmin(
            settings.keycloak_base_url,
            settings.keycloak_realm,
            settings.keycloak_admin_client_id,
            settings.keycloak_admin_client_secret.get_secret_value(),
        )
        if settings.keycloak_admin_enabled
        else NoopIdpAdmin()
    )
    s3 = build_client(
        settings.s3_endpoint,
        settings.s3_access_key.get_secret_value(),
        settings.s3_secret_key.get_secret_value(),
        settings.aws_region,
    )
    return ProvisioningActivities(
        settings=settings,
        db=Database(settings.control_db_url.get_secret_value(), pool_size=5),
        vault=Vault(build_key_service(settings)),
        store=TenantObjectStore(
            s3, ObjectStoreConfig(settings.s3_bucket, settings.s3_sse, settings.object_lock_mode)
        ),
        idp=idp,
        publisher=RedisPublisher(settings.redis_url),
        mailer=SmtpMailer(settings),
    )


async def ensure_schedules(client: Client, settings: ControlSettings) -> None:
    """Nightly audit-chain verification at 02:00 UTC (SPEC §8.5)."""
    try:
        await client.create_schedule(
            AUDIT_VERIFY_SCHEDULE_ID,
            Schedule(
                action=ScheduleActionStartWorkflow(
                    AUDIT_VERIFY_WORKFLOW,
                    id="wf:audit-verify:platform:nightly",
                    task_queue=settings.temporal_task_queue,
                ),
                spec=ScheduleSpec(cron_expressions=["0 2 * * *"]),
            ),
        )
        log.info("created schedule", extra={"schedule": AUDIT_VERIFY_SCHEDULE_ID})
    except RPCError as exc:
        if "already" not in str(exc).lower():
            raise


async def main() -> None:
    settings = get_settings()
    configure_logging("control-worker", settings.log_level)
    setup_telemetry(settings, "control-worker")
    client = await connect(settings)
    await ensure_schedules(client, settings)
    acts = build_activities(settings)
    worker = Worker(
        client,
        task_queue=settings.temporal_task_queue,
        workflows=WORKFLOWS,
        activities=acts.all(),
        interceptors=[TracingInterceptor()],
    )
    log.info("control-worker started", extra={"task_queue": settings.temporal_task_queue})
    await worker.run()


def run() -> None:
    asyncio.run(main())


if __name__ == "__main__":
    run()
