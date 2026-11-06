"""realtime-gw: hub fan-out and WebSocket auth handshake (P0-T11). No Docker: in-memory pub/sub backend."""

from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import AsyncIterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from control_api.testing import TokenFactory
from realtime_gw.hub import Hub
from realtime_gw.main import GatewaySettings, Subscription, create_app

ORG = uuid.uuid4()
TENANT = "t_abcdefghij"
USER = str(uuid.uuid4())


class MemoryBackend:
    def __init__(self) -> None:
        self.subscribed: set[str] = set()
        self.queue: asyncio.Queue[tuple[str, bytes | str]] = asyncio.Queue()
        self.closed = False

    async def subscribe(self, *channels: str) -> None:
        self.subscribed.update(channels)

    async def unsubscribe(self, *channels: str) -> None:
        self.subscribed.difference_update(channels)

    async def listen(self) -> AsyncIterator[tuple[str, bytes | str]]:
        while True:
            yield await self.queue.get()

    async def close(self) -> None:
        self.closed = True


async def test_hub_join_dispatch_leave() -> None:
    backend = MemoryBackend()
    hub = Hub(backend)
    got: list[dict[str, Any]] = []

    async def sink(e: dict[str, Any]) -> None:
        got.append(e)

    async def broken(_: dict[str, Any]) -> None:
        raise RuntimeError("client gone")

    await hub.join(["t:x:events"], sink)
    await hub.join(["t:x:events"], broken)
    assert backend.subscribed == {"t:x:events"} and hub.subscribers("t:x:events") == 2
    await hub.dispatch("t:x:events", json.dumps({"type": "provisioning.step"}))
    await hub.dispatch("t:x:events", b"not json")
    await hub.dispatch("t:other:events", json.dumps({"type": "leak"}))
    assert got == [{"channel_kind": "t", "type": "provisioning.step"}]
    await hub.leave(["t:x:events"], sink)
    assert backend.subscribed == {"t:x:events"}
    await hub.leave(["t:x:events"], broken)
    assert backend.subscribed == set()

    hub.start()
    await hub.join(["u:1:events"], sink)
    await backend.queue.put(("u:1:events", json.dumps({"type": "notification.created"})))
    for _ in range(50):
        if len(got) == 2:
            break
        await asyncio.sleep(0.01)
    assert got[-1]["type"] == "notification.created"
    await hub.stop()
    assert backend.closed


@pytest.fixture
def gateway() -> tuple[TestClient, MemoryBackend, TokenFactory]:
    tokens = TokenFactory()
    backend = MemoryBackend()

    async def lookup(token: str, org_id: uuid.UUID) -> Subscription | None:
        return Subscription(TENANT, USER) if org_id == ORG else None

    settings = GatewaySettings(allowed_origins=["http://localhost:3000"])
    app = create_app(settings, Hub(backend), tokens.validator(), lookup)
    return TestClient(app), backend, tokens


def test_ws_auth_subscribes_only_the_members_channels(
    gateway: tuple[TestClient, MemoryBackend, TokenFactory],
) -> None:
    client, backend, tokens = gateway
    token = tokens.customer("sub-1", "a@example.test")
    with client, client.websocket_connect("/v1/events", headers={"origin": "http://localhost:3000"}) as ws:
        ws.send_text(json.dumps({"type": "auth", "token": token, "org_id": str(ORG)}))
        assert ws.receive_json() == {"type": "ready", "org_id": str(ORG)}
        assert backend.subscribed == {f"t:{TENANT}:events", f"u:{USER}:events"}
        ws.send_text("ping")
        assert ws.receive_text() == "pong"


@pytest.mark.parametrize(
    "message",
    [
        {"type": "hello"},
        {"type": "auth", "token": "junk", "org_id": str(ORG)},
        {"type": "auth", "org_id": str(ORG)},
        {"type": "auth", "token": "x", "org_id": "not-a-uuid"},
    ],
)
def test_ws_rejects_bad_auth(
    gateway: tuple[TestClient, MemoryBackend, TokenFactory], message: dict[str, str]
) -> None:
    client, backend, _ = gateway
    with client, client.websocket_connect("/v1/events") as ws:
        ws.send_text(json.dumps(message))
        with pytest.raises(Exception):
            ws.receive_json()
    assert backend.subscribed == set()


def test_ws_rejects_non_members_and_staff(gateway: tuple[TestClient, MemoryBackend, TokenFactory]) -> None:
    client, backend, tokens = gateway
    for token, org in (
        (tokens.customer("sub-2", "b@example.test"), uuid.uuid4()),
        (tokens.staff("staff-1", ["staff_admin"]), ORG),
    ):
        with client, client.websocket_connect("/v1/events") as ws:
            ws.send_text(json.dumps({"type": "auth", "token": token, "org_id": str(org)}))
            with pytest.raises(Exception):
                ws.receive_json()
    assert backend.subscribed == set()


def test_ws_rejects_foreign_origin(gateway: tuple[TestClient, MemoryBackend, TokenFactory]) -> None:
    client, _, _ = gateway
    with (
        client,
        pytest.raises(Exception),
        client.websocket_connect("/v1/events", headers={"origin": "https://evil.example"}) as ws,
    ):
        ws.receive_json()


def test_health(gateway: tuple[TestClient, MemoryBackend, TokenFactory]) -> None:
    client, _, _ = gateway
    with client:
        assert client.get("/healthz").json() == {"status": "ok"}


async def test_redis_backend_with_fakeredis() -> None:
    from fakeredis import FakeAsyncRedis

    from realtime_gw.hub import RedisBackend

    redis = FakeAsyncRedis()
    backend = RedisBackend("redis://unused", client=redis)
    hub = Hub(backend)
    got: list[dict[str, Any]] = []

    async def sink(e: dict[str, Any]) -> None:
        got.append(e)

    hub.start()
    await hub.join([f"t:{TENANT}:events"], sink)
    for _ in range(100):
        await redis.publish(f"t:{TENANT}:events", json.dumps({"type": "tenant.provisioned"}))
        await asyncio.sleep(0.05)
        if got:
            break
    assert got and got[0]["type"] == "tenant.provisioned"
    await hub.leave([f"t:{TENANT}:events"], sink)
    await hub.stop()


async def test_control_api_lookup() -> None:
    import httpx
    import respx

    from realtime_gw.main import control_api_lookup

    me = {"user": {"id": USER}, "memberships": [{"org_id": str(ORG), "tenant_id": TENANT}]}
    with respx.mock(base_url="http://control.test") as mock:
        mock.get("/v1/me").mock(return_value=httpx.Response(200, json=me))
        lookup = control_api_lookup("http://control.test/")
        assert await lookup("tok", ORG) == Subscription(TENANT, USER)
        assert await lookup("tok", uuid.uuid4()) is None
        mock.get("/v1/me").mock(return_value=httpx.Response(401))
        assert await lookup("tok", ORG) is None


def test_ws_filters_other_org_notifications_and_relays_events(
    gateway: tuple[TestClient, MemoryBackend, TokenFactory],
) -> None:
    client, backend, tokens = gateway
    token = tokens.customer("sub-3", "c@example.test")
    with client, client.websocket_connect("/v1/events") as ws:
        ws.send_text(json.dumps({"type": "auth", "token": token, "org_id": str(ORG)}))
        assert ws.receive_json()["type"] == "ready"
        client.portal.call(
            backend.queue.put,
            (f"u:{USER}:events", json.dumps({"type": "notification.created", "org_id": str(uuid.uuid4())})),
        )
        client.portal.call(
            backend.queue.put, (f"t:{TENANT}:events", json.dumps({"type": "provisioning.step"}))
        )
        assert ws.receive_json() == {"channel_kind": "t", "type": "provisioning.step"}
