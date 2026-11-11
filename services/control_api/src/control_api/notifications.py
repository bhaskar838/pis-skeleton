"""In-app + e-mail notifications with per-user preferences (G-06, X-01)."""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from control_api.mailer import Mail, Mailer
from control_api.models import AppUser, Notification, NotificationPreference
from control_api.realtime import Publisher, user_channel

# Event types a user can configure in G-06. Default: in-app on, e-mail on.
EVENT_TYPES: dict[str, str] = {
    "tenant.provisioned": "Your workspace is ready",
    "member.joined": "A new member joined your organisation",
    "member.role_changed": "Your role changed",
    "member.removed": "You were removed from an organisation",
}


async def preferences(
    session: AsyncSession, user_ids: Iterable[uuid.UUID], org_id: uuid.UUID, event_type: str
) -> dict[uuid.UUID, tuple[bool, bool]]:
    rows = await session.execute(
        select(
            NotificationPreference.user_id, NotificationPreference.in_app, NotificationPreference.email
        ).where(
            NotificationPreference.org_id == org_id,
            NotificationPreference.event_type == event_type,
            NotificationPreference.user_id.in_(list(user_ids)),
        )
    )
    return {r.user_id: (r.in_app, r.email) for r in rows}


async def notify(
    session: AsyncSession,
    publisher: Publisher,
    mailer: Mailer,
    *,
    org_id: uuid.UUID,
    user_ids: list[uuid.UUID],
    event_type: str,
    payload: dict[str, Any],
    link: str | None = None,
) -> list[Notification]:
    if event_type not in EVENT_TYPES:
        raise ValueError(f"unknown notification type {event_type}")
    if not user_ids:
        return []
    prefs = await preferences(session, user_ids, org_id, event_type)
    result = await session.execute(select(AppUser.id, AppUser.email).where(AppUser.id.in_(user_ids)))
    emails: dict[uuid.UUID, str] = {}
    for row in result:
        emails[row[0]] = row[1]
    created: list[Notification] = []
    body = {**payload, **({"link": link} if link else {})}
    for uid in user_ids:
        in_app, email = prefs.get(uid, (True, True))
        if in_app:
            n = Notification(org_id=org_id, user_id=uid, type=event_type, payload=body)
            session.add(n)
            created.append(n)
        if email and uid in emails:
            text = f"{EVENT_TYPES[event_type]}.\n\n{payload.get('message', '')}\n\n{link or ''}".strip()
            await mailer.send(
                Mail(to=emails[uid], subject=f"{{product}}: {EVENT_TYPES[event_type]}", text=text)
            )
    await session.flush()
    for n in created:
        await publisher.publish(
            user_channel(n.user_id),
            {
                "type": "notification.created",
                "org_id": str(org_id),
                "notification": {"id": str(n.id), "type": n.type, "payload": n.payload},
            },
        )
    return created
