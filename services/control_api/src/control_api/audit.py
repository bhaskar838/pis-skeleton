"""``audit.emit()`` and chain verification on the Control DB (SPEC §8.5, P0-T9)."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from control_api.models import AuditEvent, AuditVerificationRun
from dcs_common.audit import (
    GENESIS_HASH,
    PLATFORM_CHAIN,
    Anchor,
    AuditFields,
    ChainVerification,
    StoredAuditEvent,
    compute_hash,
    normalise_ip,
    verify_chain,
)
from dcs_common.logging import redact


@dataclass(frozen=True)
class Actor:
    type: str  # user | staff | system | api_key
    id: str | None
    ip: str | None = None
    ua: str | None = None

    @classmethod
    def system(cls, component: str) -> Actor:
        return cls("system", component)


def _chain_filter(org_id: uuid.UUID | None) -> Any:
    return AuditEvent.org_id.is_(None) if org_id is None else AuditEvent.org_id == org_id


async def emit(
    session: AsyncSession,
    *,
    actor: Actor,
    action: str,
    org_id: uuid.UUID | None,
    target_type: str | None = None,
    target_id: str | None = None,
    details: Mapping[str, Any] | None = None,
) -> AuditEvent:
    """Append one event to the org's chain inside the caller's transaction.

    The per-chain advisory lock serialises appends, so ``prev_hash`` always points at the latest event.
    ``details`` are passed through the log redactor: secrets and raw PII never reach the audit log.
    """
    chain = org_id or PLATFORM_CHAIN
    await session.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:k, 0))"), {"k": f"dcs.audit:{chain}"}
    )
    prev = await session.scalar(
        select(AuditEvent.hash).where(_chain_filter(org_id)).order_by(AuditEvent.id.desc()).limit(1)
    )
    clean_details = redact(dict(details or {}))
    fields = AuditFields(
        ts=datetime.now(UTC),
        org_id=org_id,
        actor_type=actor.type,
        actor_id=actor.id,
        action=action,
        target_type=target_type,
        target_id=target_id,
        ip=normalise_ip(actor.ip),
        ua=(actor.ua or None) and actor.ua[:512],
        details=clean_details,
    )
    prev_hash = prev or GENESIS_HASH
    event = AuditEvent(
        ts=fields.ts,
        org_id=org_id,
        actor_type=fields.actor_type,
        actor_id=fields.actor_id,
        action=fields.action,
        target_type=fields.target_type,
        target_id=fields.target_id,
        ip=fields.ip,
        ua=fields.ua,
        details=dict(fields.details),
        prev_hash=prev_hash,
        hash=compute_hash(prev_hash, fields),
    )
    session.add(event)
    await session.flush()
    return event


def to_stored(row: AuditEvent) -> StoredAuditEvent:
    return StoredAuditEvent(
        id=row.id,
        fields=AuditFields(
            ts=row.ts,
            org_id=row.org_id,
            actor_type=row.actor_type,
            actor_id=row.actor_id,
            action=row.action,
            target_type=row.target_type,
            target_id=row.target_id,
            ip=str(row.ip) if row.ip is not None else None,
            ua=row.ua,
            details=row.details or {},
        ),
        prev_hash=bytes(row.prev_hash),
        hash=bytes(row.hash),
    )


async def _iter_chain(session: AsyncSession, org_id: uuid.UUID | None) -> AsyncIterator[StoredAuditEvent]:
    stream = await session.stream_scalars(
        select(AuditEvent)
        .where(_chain_filter(org_id))
        .order_by(AuditEvent.id)
        .execution_options(yield_per=1000)
    )
    async for row in stream:
        yield to_stored(row)


async def verify_org_chain(session: AsyncSession, org_id: uuid.UUID | None) -> ChainVerification:
    """Verify one chain (platform scope) against the last successful anchor, and record the run."""
    chain = org_id or PLATFORM_CHAIN
    last_ok = await session.scalar(
        select(AuditVerificationRun)
        .where(AuditVerificationRun.chain == chain, AuditVerificationRun.ok.is_(True))
        .where(AuditVerificationRun.last_event_id.is_not(None))
        .order_by(AuditVerificationRun.id.desc())
        .limit(1)
    )
    anchor = (
        Anchor(last_ok.last_event_id, bytes(last_ok.last_hash))
        if last_ok is not None and last_ok.last_event_id is not None and last_ok.last_hash is not None
        else None
    )
    events = [ev async for ev in _iter_chain(session, org_id)]
    result = verify_chain(events, anchor)
    session.add(
        AuditVerificationRun(
            chain=chain,
            ok=result.ok,
            checked=result.checked,
            last_event_id=result.last_id,
            last_hash=result.last_hash,
            first_bad_id=result.first_bad_id,
            reason=result.reason,
        )
    )
    await session.flush()
    return result


async def chains(session: AsyncSession) -> list[uuid.UUID | None]:
    rows = await session.execute(select(AuditEvent.org_id).distinct())
    return [r[0] for r in rows]
