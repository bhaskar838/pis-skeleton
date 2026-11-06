"""Process-wide dependencies, created once at startup and stored on ``app.state.dcs``."""

from __future__ import annotations

import base64
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from control_api.db import Database
from control_api.mailer import Mailer, SmtpMailer
from control_api.realtime import Publisher, RedisPublisher
from control_api.settings import ControlSettings
from dcs_authz import Policy, default_policy
from dcs_common.auth import JwksCache, TokenValidator
from dcs_vault import AwsKmsKeyService, KeyService, LocalKeyService, Vault

if TYPE_CHECKING:
    from temporalio.client import Client


class WorkflowStarter:
    """Lazily connects to Temporal; replaced by a fake in unit tests."""

    def __init__(self, settings: ControlSettings) -> None:
        self._settings = settings
        self._client: Client | None = None

    async def client(self) -> Client:
        if self._client is None:
            from control_api.temporal import connect

            self._client = await connect(self._settings)
        return self._client

    async def start(
        self, workflow: str, arg: object, *, workflow_id: str, allow_retry_failed: bool = False
    ) -> str:
        from temporalio.common import WorkflowIDReusePolicy
        from temporalio.exceptions import WorkflowAlreadyStartedError

        client = await self.client()
        policy = (
            WorkflowIDReusePolicy.ALLOW_DUPLICATE_FAILED_ONLY
            if allow_retry_failed
            else WorkflowIDReusePolicy.REJECT_DUPLICATE
        )
        try:
            handle = await client.start_workflow(
                workflow,
                arg,
                id=workflow_id,
                task_queue=self._settings.temporal_task_queue,
                id_reuse_policy=policy,
            )
            return handle.id
        except WorkflowAlreadyStartedError:
            return workflow_id  # idempotent: the same natural key is already running / done


def build_key_service(settings: ControlSettings) -> KeyService:
    if settings.key_service == "aws":
        return AwsKmsKeyService.from_region(settings.aws_region)
    raw = settings.local_master_key.get_secret_value()
    if not raw:
        raise RuntimeError("DCS_LOCAL_MASTER_KEY is required when DCS_KEY_SERVICE=local")
    return LocalKeyService(base64.b64decode(raw), Path(settings.local_key_dir))


@dataclass
class AppState:
    settings: ControlSettings
    db: Database
    validator: TokenValidator
    workflows: WorkflowStarter
    publisher: Publisher
    mailer: Mailer
    policy: Policy = field(default_factory=default_policy)
    vault: Vault | None = None

    @classmethod
    def from_settings(cls, settings: ControlSettings) -> AppState:
        return cls(
            settings=settings,
            db=Database(settings.control_db_url.get_secret_value()),
            validator=TokenValidator(settings.issuers(), JwksCache()),
            workflows=WorkflowStarter(settings),
            publisher=RedisPublisher(settings.redis_url),
            mailer=SmtpMailer(settings),
        )

    async def close(self) -> None:
        await self.db.dispose()
        await self.publisher.close()
