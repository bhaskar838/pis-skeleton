"""control-api FastAPI application."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from control_api.routers import activity, admin, me, orgs, panel, public, team
from control_api.settings import ControlSettings, get_settings
from control_api.state import AppState
from control_api.users import UserDirectory
from dcs_common.logging import configure_logging
from dcs_common.telemetry import setup_telemetry
from dcs_common.web import install_common

API_DESCRIPTION = """
DCS-PIS control plane. All routes use OIDC bearer tokens. Customer routes take the active organisation from the
`X-DCS-Org` header; staff routes live under `/v1/admin` and need a staff-realm token. Errors are RFC 9457
problem+json.
"""


def create_app(settings: ControlSettings | None = None, state: AppState | None = None) -> FastAPI:
    settings = settings or get_settings()
    app_state = state or AppState.from_settings(settings)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield
        await app_state.close()

    app = FastAPI(
        title="DCS-PIS control-api",
        version="0.0.1",
        description=API_DESCRIPTION,
        lifespan=lifespan,
        openapi_url="/openapi.json",
    )
    app.state.dcs = app_state
    app.state.users = UserDirectory(app_state.db)
    install_common(
        app, hsts=settings.is_production_like or settings.env == "local", ready_check=app_state.db.ping
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE"],
        allow_headers=["Authorization", "Content-Type", "X-DCS-Org", "Idempotency-Key", "X-Request-Id"],
    )
    for router in (
        me.router,
        orgs.router,
        team.router,
        activity.router,
        admin.router,
        panel.router,
        public.router,
    ):
        app.include_router(router)
    return app


def build() -> FastAPI:
    settings = get_settings()
    configure_logging("control-api", settings.log_level)
    app = create_app(settings)
    setup_telemetry(settings, "control-api", app)
    return app


def run() -> None:
    uvicorn.run("control_api.main:build", factory=True, host="0.0.0.0", port=8000, proxy_headers=True)  # noqa: S104


if __name__ == "__main__":
    run()
