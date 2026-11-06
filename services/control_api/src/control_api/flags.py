"""Feature flags: global < plan < org (M-13). Unknown keys fall back to code defaults."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from control_api.models import FeatureFlag

DEFAULTS: dict[str, Any] = {
    "system.maintenance": False,
    "system.signup_enabled": True,
    "ui.insights_feed": False,
}

_PRECEDENCE = {"global": 0, "plan": 1, "org": 2}


async def effective_flags(
    session: AsyncSession, org_id: uuid.UUID | None, plan_id: str | None
) -> dict[str, Any]:
    conds = [FeatureFlag.scope == "global"]
    if plan_id:
        conds.append((FeatureFlag.scope == "plan") & (FeatureFlag.scope_id == plan_id))
    if org_id:
        conds.append((FeatureFlag.scope == "org") & (FeatureFlag.scope_id == str(org_id)))
    rows = (await session.scalars(select(FeatureFlag).where(or_(*conds)))).all()
    out = dict(DEFAULTS)
    for row in sorted(rows, key=lambda r: _PRECEDENCE[r.scope]):
        out[row.key] = row.value
    return out
