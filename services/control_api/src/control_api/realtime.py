"""Publish live events for realtime-gw (Redis pub/sub). Channels are always tenant- or user-scoped."""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any, Protocol

from dcs_common.ids import is_tenant_id

log = logging.getLogger(__name__)


def org_channel(tenant_id: str) -> str:
    if not is_tenant_id(tenant_id):
        raise ValueError("invalid tenant id")
    return f"t:{tenant_id}:events"


def user_channel(user_id: uuid.UUID) -> str:
    return f"u:{user_id}:events"


class Publisher(Protocol):
    async def publish(self, channel: str, event: dict[str, Any]) -> None: ...

    async def close(self) -> None: ...


class RedisPublisher:
    def __init__(self, url: str) -> None:
        from redis.asyncio import Redis

        self._redis = Redis.from_url(url)

    async def publish(self, channel: str, event: dict[str, Any]) -> None:
        try:
            await self._redis.publish(channel, json.dumps(event, default=str))
        except Exception:  # noqa: BLE001 - live updates are best-effort; state is in the DB
            log.warning("realtime publish failed", extra={"channel": channel})

    async def close(self) -> None:
        await self._redis.aclose()


class MemoryPublisher:
    """In-process publisher for tests."""

    def __init__(self) -> None:
        self.events: list[tuple[str, dict[str, Any]]] = []

    async def publish(self, channel: str, event: dict[str, Any]) -> None:
        self.events.append((channel, event))

    async def close(self) -> None:
        return None
