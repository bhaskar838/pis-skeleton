"""Mirror Keycloak identities into ``app_user`` (SPEC §11.1: "mirror of Keycloak IDs")."""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError

from control_api.db import Database
from control_api.models import AppUser
from dcs_common.auth import Principal
from dcs_common.ids import uuid7
from dcs_common.problem import ProblemError, forbidden


@dataclass(frozen=True)
class UserRef:
    id: uuid.UUID
    email: str
    name: str | None


class UserDirectory:
    def __init__(self, db: Database, *, ttl_s: float = 60.0) -> None:
        self._db = db
        self._ttl = ttl_s
        self._cache: dict[str, tuple[UserRef, float]] = {}

    async def ensure(self, principal: Principal) -> UserRef:
        if principal.is_staff:
            raise forbidden("Staff accounts cannot use customer routes.")
        hit = self._cache.get(principal.subject)
        if hit is not None and hit[1] > time.monotonic() and hit[0].email == (principal.email or "").lower():
            return hit[0]
        if not principal.email:
            raise forbidden("Your account has no e-mail address.")
        email = principal.email.lower()
        stmt = (
            insert(AppUser)
            .values(
                id=uuid7(),
                keycloak_sub=principal.subject,
                email=email,
                name=principal.name,
                last_seen_at=datetime.now(UTC),
            )
            .on_conflict_do_update(
                index_elements=[AppUser.keycloak_sub],
                set_={"email": email, "name": principal.name, "last_seen_at": datetime.now(UTC)},
            )
            .returning(AppUser.id, AppUser.email, AppUser.name)
        )
        try:
            async with self._db.unscoped_tx() as session:
                row = (await session.execute(stmt)).one()
        except IntegrityError:
            raise ProblemError(
                409, slug="email-in-use", detail="This e-mail address belongs to another account."
            ) from None
        ref = UserRef(id=row.id, email=row.email, name=row.name)
        self._cache[principal.subject] = (ref, time.monotonic() + self._ttl)
        return ref

    def forget(self, subject: str) -> None:
        self._cache.pop(subject, None)
