"""Channel hub: one Redis pub/sub connection per process, fanned out to WebSocket clients.

Channel names are produced only by the server from a verified membership:
``t:<tenant_id>:events`` (org-wide) and ``u:<user_id>:events`` (personal). Clients never name channels.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from collections import defaultdict
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any, Protocol

log = logging.getLogger(__name__)

Sink = Callable[[dict[str, Any]], Awaitable[None]]


class PubSubBackend(Protocol):
    async def subscribe(self, *channels: str) -> None: ...

    async def unsubscribe(self, *channels: str) -> None: ...

    def listen(self) -> AsyncIterator[tuple[str, bytes | str]]: ...

    async def close(self) -> None: ...


class RedisBackend:
    def __init__(self, url: str, client: Any | None = None) -> None:
        from redis.asyncio import Redis

        self._redis = client if client is not None else Redis.from_url(url)
        self._ps = self._redis.pubsub(ignore_subscribe_messages=True)

    async def subscribe(self, *channels: str) -> None:
        await self._ps.subscribe(*channels)

    async def unsubscribe(self, *channels: str) -> None:
        await self._ps.unsubscribe(*channels)

    async def listen(self) -> AsyncIterator[tuple[str, bytes | str]]:
        while True:
            if not self._ps.subscribed:
                await asyncio.sleep(0.2)
                continue
            msg = await self._ps.get_message(timeout=1.0)
            if msg and msg.get("type") == "message":
                ch = msg["channel"].decode() if isinstance(msg["channel"], bytes) else msg["channel"]
                yield ch, msg["data"]

    async def close(self) -> None:
        await self._ps.aclose()
        await self._redis.aclose()


class Hub:
    def __init__(self, backend: PubSubBackend) -> None:
        self._backend = backend
        self._sinks: dict[str, set[Sink]] = defaultdict(set)
        self._lock = asyncio.Lock()
        self._task: asyncio.Task[None] | None = None

    def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._pump())

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
        await self._backend.close()

    async def join(self, channels: list[str], sink: Sink) -> None:
        async with self._lock:
            new = [c for c in channels if not self._sinks.get(c)]
            for c in channels:
                self._sinks[c].add(sink)
            if new:
                await self._backend.subscribe(*new)

    async def leave(self, channels: list[str], sink: Sink) -> None:
        async with self._lock:
            empty = []
            for c in channels:
                self._sinks[c].discard(sink)
                if not self._sinks[c]:
                    empty.append(c)
                    del self._sinks[c]
            if empty:
                await self._backend.unsubscribe(*empty)

    def subscribers(self, channel: str) -> int:
        return len(self._sinks.get(channel, ()))

    async def dispatch(self, channel: str, data: bytes | str) -> None:
        try:
            event = json.loads(data)
        except (ValueError, TypeError):
            log.warning("dropping non-JSON event", extra={"channel": channel})
            return
        for sink in list(self._sinks.get(channel, ())):
            try:
                await sink({"channel_kind": channel.split(":", 1)[0], **event})
            except Exception:
                log.debug("sink failed", exc_info=True)

    async def _pump(self) -> None:
        while True:
            try:
                async for channel, data in self._backend.listen():
                    await self.dispatch(channel, data)
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("pub/sub listener crashed; retrying")
                await asyncio.sleep(1.0)
