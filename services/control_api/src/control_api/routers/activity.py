"""Audit log (G-04), notifications (X-01, G-06), flags and security summary (G-03)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import select, update

from control_api.deps import OrgContext, StateDep, require
from control_api.flags import effective_flags
from control_api.models import AuditEvent, Notification, NotificationPreference, Org
from control_api.notifications import EVENT_TYPES
from control_api.schemas import (
    AuditEventOut,
    FlagsOut,
    NotificationOut,
    NotificationPref,
    NotificationPrefsIn,
    NotificationPrefsOut,
    Page,
    SecuritySummary,
)
from dcs_common.problem import PROBLEM_RESPONSES, ProblemError, not_found

router = APIRouter(prefix="/v1", tags=["activity"], responses=PROBLEM_RESPONSES)

AuditRead = Annotated[OrgContext, Depends(require("audit:read"))]
NotifRead = Annotated[OrgContext, Depends(require("notifications:read"))]


def audit_out(e: AuditEvent) -> AuditEventOut:
    return AuditEventOut(
        id=e.id,
        ts=e.ts,
        org_id=e.org_id,
        actor_type=e.actor_type,
        actor_id=e.actor_id,
        action=e.action,
        target_type=e.target_type,
        target_id=e.target_id,
        ip=str(e.ip) if e.ip is not None else None,
        details=e.details or {},
    )


def _int_cursor(cursor: str | None) -> int | None:
    if cursor is None:
        return None
    if not cursor.isdigit():
        raise ProblemError(400, slug="bad-cursor", detail="Invalid cursor.")
    return int(cursor)


@router.get(
    "/audit", response_model=Page[AuditEventOut], summary="Audit log of the active org (incl. staff access)"
)
async def list_audit(
    state: StateDep,
    ctx: AuditRead,
    cursor: str | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    action: Annotated[str | None, Query(max_length=100)] = None,
    actor_type: Annotated[str | None, Query(pattern="^(user|staff|system|api_key)$")] = None,
) -> Page[AuditEventOut]:
    before = _int_cursor(cursor)
    q = select(AuditEvent).where(AuditEvent.org_id == ctx.org_id)
    if before is not None:
        q = q.where(AuditEvent.id < before)
    if action:
        q = q.where(AuditEvent.action.startswith(action))
    if actor_type:
        q = q.where(AuditEvent.actor_type == actor_type)
    async with state.db.org_tx(ctx.org_id, ctx.user.id) as s:
        rows = (await s.scalars(q.order_by(AuditEvent.id.desc()).limit(limit + 1))).all()
    items = [audit_out(e) for e in rows[:limit]]
    return Page(items=items, next_cursor=str(rows[limit - 1].id) if len(rows) > limit else None)


@router.get(
    "/notifications", response_model=Page[NotificationOut], summary="Your notifications in the active org"
)
async def list_notifications(
    state: StateDep,
    ctx: NotifRead,
    cursor: uuid.UUID | None = None,
    unread_only: bool = False,
    limit: Annotated[int, Query(ge=1, le=100)] = 30,
) -> Page[NotificationOut]:
    q = select(Notification).where(Notification.org_id == ctx.org_id, Notification.user_id == ctx.user.id)
    if cursor is not None:
        q = q.where(Notification.id < cursor)
    if unread_only:
        q = q.where(Notification.read_at.is_(None))
    async with state.db.org_tx(ctx.org_id, ctx.user.id) as s:
        rows = (await s.scalars(q.order_by(Notification.id.desc()).limit(limit + 1))).all()
    items = [
        NotificationOut(id=n.id, type=n.type, payload=n.payload, read_at=n.read_at, created_at=n.created_at)
        for n in rows[:limit]
    ]
    return Page(items=items, next_cursor=str(rows[limit - 1].id) if len(rows) > limit else None)


@router.post("/notifications/{notification_id}/read", status_code=204, summary="Mark one notification read")
async def mark_read(notification_id: uuid.UUID, state: StateDep, ctx: NotifRead) -> Response:
    async with state.db.org_tx(ctx.org_id, ctx.user.id) as s:
        result = await s.execute(
            update(Notification)
            .where(
                Notification.id == notification_id,
                Notification.org_id == ctx.org_id,
                Notification.user_id == ctx.user.id,
            )
            .values(read_at=datetime.now(UTC))
        )
    if result.rowcount == 0:  # type: ignore[attr-defined]
        raise not_found()
    return Response(status_code=204)


@router.post("/notifications/read-all", status_code=204, summary="Mark all notifications read")
async def mark_all_read(state: StateDep, ctx: NotifRead) -> Response:
    async with state.db.org_tx(ctx.org_id, ctx.user.id) as s:
        await s.execute(
            update(Notification)
            .where(
                Notification.org_id == ctx.org_id,
                Notification.user_id == ctx.user.id,
                Notification.read_at.is_(None),
            )
            .values(read_at=datetime.now(UTC))
        )
    return Response(status_code=204)


@router.get(
    "/notification-preferences", response_model=NotificationPrefsOut, summary="Your notification settings"
)
async def get_prefs(state: StateDep, ctx: NotifRead) -> NotificationPrefsOut:
    async with state.db.org_tx(ctx.org_id, ctx.user.id) as s:
        rows = {
            p.event_type: p
            for p in (
                await s.scalars(
                    select(NotificationPreference).where(
                        NotificationPreference.org_id == ctx.org_id,
                        NotificationPreference.user_id == ctx.user.id,
                    )
                )
            ).all()
        }
    items = [
        NotificationPref(
            event_type=t,
            email=rows[t].email if t in rows else True,
            in_app=rows[t].in_app if t in rows else True,
        )
        for t in EVENT_TYPES
    ]
    return NotificationPrefsOut(items=items, event_types=EVENT_TYPES)


@router.put(
    "/notification-preferences", response_model=NotificationPrefsOut, summary="Update notification settings"
)
async def put_prefs(body: NotificationPrefsIn, state: StateDep, ctx: NotifRead) -> NotificationPrefsOut:
    unknown = [p.event_type for p in body.items if p.event_type not in EVENT_TYPES]
    if unknown:
        raise ProblemError(422, detail=f"Unknown event types: {', '.join(unknown)}")
    from sqlalchemy.dialects.postgresql import insert

    async with state.db.org_tx(ctx.org_id, ctx.user.id) as s:
        for p in body.items:
            stmt = (
                insert(NotificationPreference)
                .values(
                    user_id=ctx.user.id,
                    org_id=ctx.org_id,
                    event_type=p.event_type,
                    email=p.email,
                    in_app=p.in_app,
                )
                .on_conflict_do_update(
                    index_elements=["user_id", "org_id", "event_type"],
                    set_={"email": p.email, "in_app": p.in_app},
                )
            )
            await s.execute(stmt)
    return await get_prefs(state, ctx)


@router.get("/flags", response_model=FlagsOut, summary="Effective feature flags for the active org")
async def get_flags(state: StateDep, ctx: Annotated[OrgContext, Depends(require("flags:read"))]) -> FlagsOut:
    async with state.db.org_tx(ctx.org_id, ctx.user.id) as s:
        org = await s.get(Org, ctx.org_id)
        flags = await effective_flags(s, ctx.org_id, org.plan_id if org else None)
    return FlagsOut(flags=flags)


@router.get("/security/summary", response_model=SecuritySummary, summary="Security settings overview (G-03)")
async def security_summary(
    state: StateDep, ctx: Annotated[OrgContext, Depends(require("security:read"))]
) -> SecuritySummary:
    roles = [r for r in state.policy.roles_in_scope("customer") if state.policy.mfa_required(r)]
    return SecuritySummary(
        mfa_required_roles=roles,
        your_role_requires_mfa=state.policy.mfa_required(ctx.role),
        session_mfa=ctx.principal.has_mfa(),
        account_console_url=f"{state.settings.oidc_issuer.rstrip('/')}/account",
    )
