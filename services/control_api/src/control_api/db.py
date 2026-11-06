"""Control DB access with row-level-security scoping (SPEC §8.2).

Every transaction declares *who* it runs for, via transaction-local settings that the RLS policies read:

* ``org_tx(org_id, user_id)`` — a customer request inside one org.
* ``user_tx(user_id)``        — a customer request with no active org (e.g. ``GET /v1/me``).
* ``platform_tx()``           — staff routes and system workflows. Only code that has already checked a staff
  token or runs inside a Temporal activity may call it.

A session without any scope sees no org-scoped rows at all.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from contextlib import AbstractAsyncContextManager, asynccontextmanager

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine


class Database:
    def __init__(self, url: str, *, echo: bool = False, pool_size: int = 10) -> None:
        self.engine: AsyncEngine = create_async_engine(
            url, echo=echo, pool_size=pool_size, max_overflow=pool_size, pool_pre_ping=True
        )
        self._sessions = async_sessionmaker(self.engine, expire_on_commit=False)

    async def dispose(self) -> None:
        await self.engine.dispose()

    async def ping(self) -> bool:
        try:
            async with self.engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            return True
        except Exception:  # noqa: BLE001 - readiness probe must not raise
            return False

    @asynccontextmanager
    async def _tx(self, settings: dict[str, str]) -> AsyncIterator[AsyncSession]:
        async with self._sessions() as session, session.begin():
            for key, value in settings.items():
                await session.execute(text("SELECT set_config(:k, :v, true)"), {"k": key, "v": value})
            yield session

    def org_tx(
        self, org_id: uuid.UUID, user_id: uuid.UUID | None
    ) -> AbstractAsyncContextManager[AsyncSession]:
        cfg = {"app.org_id": str(org_id)}
        if user_id is not None:
            cfg["app.user_id"] = str(user_id)
        return self._tx(cfg)

    def user_tx(self, user_id: uuid.UUID) -> AbstractAsyncContextManager[AsyncSession]:
        return self._tx({"app.user_id": str(user_id)})

    def platform_tx(self) -> AbstractAsyncContextManager[AsyncSession]:
        return self._tx({"app.scope": "platform"})

    def unscoped_tx(self) -> AbstractAsyncContextManager[AsyncSession]:
        """For tables without RLS only (``app_user``, ``feature_flag``)."""
        return self._tx({})
