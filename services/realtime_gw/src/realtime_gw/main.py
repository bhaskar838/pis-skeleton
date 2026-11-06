"""WebSocket endpoint ``/v1/events`` (SPEC §10.1 ``WS /v1/events``).

Protocol (browsers cannot set WebSocket headers, and query-string tokens leak into logs):

1. client connects;
2. client sends ``{"type": "auth", "token": "<access token>", "org_id": "<uuid>"}`` within 5 s;
3. the gateway validates the token, asks control-api ``GET /v1/me`` (with that token) for memberships, and
   subscribes the socket to the org channel and the user's personal channel;
4. server sends ``{"type": "ready"}``, then events; the socket closes when the token expires (client reconnects).
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

import httpx
import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from pydantic import Field

from dcs_common.auth import JwksCache, Principal, TokenError, TokenValidator
from dcs_common.logging import configure_logging
from dcs_common.settings import DcsSettings
from dcs_common.telemetry import setup_telemetry
from dcs_common.web import install_common
from realtime_gw.hub import Hub, RedisBackend

AUTH_TIMEOUT_S = 5.0
PING_INTERVAL_S = 25.0


class GatewaySettings(DcsSettings):
    service_name: str = "realtime-gw"
    redis_url: str = "redis://localhost:6379/0"
    control_api_url: str = "http://localhost:8001"
    oidc_issuer: str = "http://keycloak.localhost:8080/realms/dcs"
    oidc_audience: str = "dcs-api"
    oidc_jwks_url: str | None = None
    allowed_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3000"])


@lru_cache(maxsize=1)
def get_settings() -> GatewaySettings:
    return GatewaySettings()


@dataclass(frozen=True)
class Subscription:
    tenant_id: str
    user_id: str


MembershipLookup = Callable[[str, uuid.UUID], Awaitable[Subscription | None]]


def control_api_lookup(base_url: str) -> MembershipLookup:
    async def _lookup(token: str, org_id: uuid.UUID) -> Subscription | None:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(
                f"{base_url.rstrip('/')}/v1/me", headers={"Authorization": f"Bearer {token}"}
            )
        if resp.status_code != 200:
            return None
        me = resp.json()
        for m in me.get("memberships", []):
            if m.get("org_id") == str(org_id):
                return Subscription(tenant_id=m["tenant_id"], user_id=me["user"]["id"])
        return None

    return _lookup


def create_app(
    settings: GatewaySettings | None = None,
    hub: Hub | None = None,
    validator: TokenValidator | None = None,
    lookup: MembershipLookup | None = None,
) -> FastAPI:
    settings = settings or get_settings()
    the_hub = hub or Hub(RedisBackend(settings.redis_url))
    jwks = settings.oidc_jwks_url or f"{settings.oidc_issuer.rstrip('/')}/protocol/openid-connect/certs"
    from dcs_common.auth import IssuerConfig

    the_validator = validator or TokenValidator(
        [IssuerConfig("customer", settings.oidc_issuer, settings.oidc_audience, jwks)], JwksCache()
    )
    the_lookup = lookup or control_api_lookup(settings.control_api_url)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        the_hub.start()
        yield
        await the_hub.stop()

    app = FastAPI(title="DCS-PIS realtime-gw", version="0.0.1", lifespan=lifespan)
    install_common(app, hsts=True)

    @app.websocket("/v1/events")
    async def events(ws: WebSocket) -> None:
        origin = ws.headers.get("origin")
        if origin is not None and origin not in settings.allowed_origins:
            await ws.close(code=4403)
            return
        await ws.accept()
        try:
            raw = await asyncio.wait_for(ws.receive_text(), timeout=AUTH_TIMEOUT_S)
            msg = json.loads(raw)
            if msg.get("type") != "auth":
                raise ValueError("expected auth")
            token = str(msg["token"])
            org_id = uuid.UUID(str(msg["org_id"]))
            principal: Principal = await the_validator.validate(token)
            if principal.is_staff:
                raise PermissionError("staff tokens are not accepted")
            sub = await the_lookup(token, org_id)
            if sub is None:
                raise PermissionError("not a member")
        except (TimeoutError, ValueError, KeyError, TokenError, PermissionError, WebSocketDisconnect):
            with contextlib.suppress(Exception):
                await ws.close(code=4401)
            return

        channels = [f"t:{sub.tenant_id}:events", f"u:{sub.user_id}:events"]
        send_lock = asyncio.Lock()

        async def sink(event: dict[str, Any]) -> None:
            if event.get("type") == "notification.created" and event.get("org_id") not in (None, str(org_id)):
                return  # personal channel carries all orgs; show only the active org's notifications
            async with send_lock:
                await ws.send_json(event)

        await the_hub.join(channels, sink)
        expires_at = float(principal.claims.get("exp", time.time() + 300))
        try:
            await ws.send_json({"type": "ready", "org_id": str(org_id)})
            while True:
                remaining = expires_at - time.time()
                if remaining <= 0:
                    await ws.close(code=4001)  # token expired: client reconnects with a fresh token
                    break
                try:
                    incoming = await asyncio.wait_for(
                        ws.receive_text(), timeout=min(PING_INTERVAL_S, remaining)
                    )
                    if incoming == "ping":
                        async with send_lock:
                            await ws.send_text("pong")
                except TimeoutError:
                    async with send_lock:
                        await ws.send_json({"type": "ping"})
        except WebSocketDisconnect:
            pass
        finally:
            await the_hub.leave(channels, sink)

    return app


def build() -> FastAPI:
    settings = get_settings()
    configure_logging("realtime-gw", settings.log_level)
    app = create_app(settings)
    setup_telemetry(settings, "realtime-gw", app)
    return app


def run() -> None:
    uvicorn.run("realtime_gw.main:build", factory=True, host="0.0.0.0", port=8000)  # noqa: S104


if __name__ == "__main__":
    run()
