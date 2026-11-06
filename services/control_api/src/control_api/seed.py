"""`make seed`: idempotent local seed data (global feature flags). Demo tenants are created through the UI
(sign-up) so provisioning, audit and notifications run exactly as in production (SPEC §13 P0 demo script)."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from sqlalchemy.dialects.postgresql import insert

from control_api import audit
from control_api.audit import Actor
from control_api.db import Database
from control_api.flags import DEFAULTS
from control_api.models import FeatureFlag
from control_api.settings import get_settings


async def seed() -> int:
    db = Database(get_settings().control_db_url.get_secret_value(), pool_size=1)
    created = 0
    try:
        async with db.platform_tx() as s:
            for key, value in DEFAULTS.items():
                result = await s.execute(
                    insert(FeatureFlag)
                    .values(
                        key=key,
                        scope="global",
                        scope_id="",
                        value=value,
                        updated_by="seed",
                        updated_at=datetime.now(UTC),
                    )
                    .on_conflict_do_nothing()
                )
                created += result.rowcount or 0  # type: ignore[attr-defined]
            if created:
                await audit.emit(
                    s,
                    actor=Actor.system("seed"),
                    action="platform.seeded",
                    org_id=None,
                    details={"flags": created},
                )
    finally:
        await db.dispose()
    return created


def main() -> None:
    print(f"seeded {asyncio.run(seed())} feature flag(s)")


if __name__ == "__main__":
    main()
