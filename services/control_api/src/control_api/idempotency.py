"""Idempotency keys for POSTs that start work (SPEC §10)."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from control_api.models import IdempotencyRecord
from dcs_common.problem import ProblemError


def validate_key(key: str | None) -> str | None:
    if key is None:
        return None
    if not 8 <= len(key) <= 128 or not all(c.isalnum() or c in "-_." for c in key):
        raise ProblemError(
            400, slug="bad-idempotency-key", detail="Idempotency-Key must be 8-128 URL-safe chars."
        )
    return key


async def lookup(session: AsyncSession, principal: str, route: str, key: str) -> IdempotencyRecord | None:
    return await session.scalar(
        select(IdempotencyRecord).where(
            IdempotencyRecord.principal == principal,
            IdempotencyRecord.route == route,
            IdempotencyRecord.key == key,
        )
    )


def store(
    session: AsyncSession, principal: str, route: str, key: str, status: int, body: dict[str, Any]
) -> None:
    session.add(
        IdempotencyRecord(principal=principal, route=route, key=key, status_code=status, response=body)
    )
