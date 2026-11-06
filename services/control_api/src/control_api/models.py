"""Control DB ORM models, schema v1 (SPEC §11.1; P0 subset + support tables)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any, ClassVar

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import CITEXT, INET, JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from dcs_common.ids import uuid7


class Base(DeclarativeBase):
    type_annotation_map: ClassVar[dict[Any, Any]] = {dict[str, Any]: JSONB, uuid.UUID: UUID(as_uuid=True)}


def _uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid7)


def _created() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class Org(Base):
    __tablename__ = "org"
    id: Mapped[uuid.UUID] = _uuid_pk()
    tenant_id: Mapped[str] = mapped_column(String(16), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    slug: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    country: Mapped[str] = mapped_column(String(2), nullable=False)
    region: Mapped[str] = mapped_column(Text, nullable=False)
    # provisioning | active | failed | deprovisioning | deleted
    status: Mapped[str] = mapped_column(Text, nullable=False, default="provisioning")
    plan_id: Mapped[str | None] = mapped_column(Text)
    business_profile: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    profile_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    created_at: Mapped[datetime] = _created()


class AppUser(Base):
    __tablename__ = "app_user"
    id: Mapped[uuid.UUID] = _uuid_pk()
    keycloak_sub: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    email: Mapped[str] = mapped_column(CITEXT, unique=True, nullable=False)
    name: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = _created()
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Membership(Base):
    __tablename__ = "membership"
    __table_args__ = (UniqueConstraint("org_id", "user_id"),)
    id: Mapped[uuid.UUID] = _uuid_pk()
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("org.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("app_user.id", ondelete="CASCADE"), nullable=False)
    role: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="active")  # active | removed
    invited_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    created_at: Mapped[datetime] = _created()
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Invite(Base):
    __tablename__ = "invite"
    id: Mapped[uuid.UUID] = _uuid_pk()
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("org.id", ondelete="CASCADE"), nullable=False)
    email: Mapped[str] = mapped_column(CITEXT, nullable=False)
    role: Mapped[str] = mapped_column(Text, nullable=False)
    token_hash: Mapped[bytes] = mapped_column(LargeBinary, unique=True, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="pending")  # pending|accepted|revoked
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    invited_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    accepted_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = _created()


class TenantKey(Base):
    __tablename__ = "tenant_key"
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("org.id", ondelete="CASCADE"), primary_key=True)
    kms_key_arn: Mapped[str] = mapped_column(Text, nullable=False)
    wrapped_dek: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="active")  # active|pending_deletion
    deletion_scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = _created()
    rotated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class TenantDb(Base):
    __tablename__ = "tenant_db"
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("org.id", ondelete="CASCADE"), primary_key=True)
    cluster: Mapped[str] = mapped_column(Text, nullable=False)
    db_name: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    # pending | ready | dropped | failed
    status: Mapped[str] = mapped_column(Text, nullable=False, default="pending")
    cbm_version: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = _created()
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Credential(Base):
    __tablename__ = "credential"
    id: Mapped[uuid.UUID] = _uuid_pk()
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("org.id", ondelete="CASCADE"), nullable=False)
    source_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    ciphertext: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    nonce: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    aad: Mapped[str] = mapped_column(Text, nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rotated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = _created()


class AuditEvent(Base):
    __tablename__ = "audit_event"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    org_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    actor_type: Mapped[str] = mapped_column(Text, nullable=False)
    actor_id: Mapped[str | None] = mapped_column(Text)
    action: Mapped[str] = mapped_column(Text, nullable=False)
    target_type: Mapped[str | None] = mapped_column(Text)
    target_id: Mapped[str | None] = mapped_column(Text)
    ip: Mapped[str | None] = mapped_column(INET)
    ua: Mapped[str | None] = mapped_column(Text)
    details: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    prev_hash: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    hash: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)


class AuditVerificationRun(Base):
    __tablename__ = "audit_verification_run"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    ran_at: Mapped[datetime] = _created()
    chain: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    ok: Mapped[bool] = mapped_column(Boolean, nullable=False)
    checked: Mapped[int] = mapped_column(Integer, nullable=False)
    last_event_id: Mapped[int | None] = mapped_column(BigInteger)
    last_hash: Mapped[bytes | None] = mapped_column(LargeBinary)
    first_bad_id: Mapped[int | None] = mapped_column(BigInteger)
    reason: Mapped[str | None] = mapped_column(Text)


def _utcnow() -> datetime:
    return datetime.now(UTC)


class Notification(Base):
    """Rows for *other* users are inserted under RLS; Postgres applies the SELECT policy to RETURNING rows, so
    every column is generated client-side and the INSERT never needs RETURNING."""

    __tablename__ = "notification"
    __mapper_args__ = {"eager_defaults": False}  # noqa: RUF012
    id: Mapped[uuid.UUID] = _uuid_pk()
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("org.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("app_user.id", ondelete="CASCADE"), nullable=False)
    type: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, server_default=func.now(), nullable=False
    )


class NotificationPreference(Base):
    __tablename__ = "notification_preference"
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("app_user.id", ondelete="CASCADE"), primary_key=True
    )
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("org.id", ondelete="CASCADE"), primary_key=True)
    event_type: Mapped[str] = mapped_column(Text, primary_key=True)
    email: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    in_app: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class FeatureFlag(Base):
    __tablename__ = "feature_flag"
    key: Mapped[str] = mapped_column(Text, primary_key=True)
    scope: Mapped[str] = mapped_column(Text, primary_key=True)  # global | plan | org
    scope_id: Mapped[str] = mapped_column(Text, primary_key=True, default="")
    value: Mapped[Any] = mapped_column(JSONB, nullable=False)
    updated_by: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime] = _created()


class IdempotencyRecord(Base):
    __tablename__ = "idempotency_record"
    principal: Mapped[str] = mapped_column(Text, primary_key=True)
    route: Mapped[str] = mapped_column(Text, primary_key=True)
    key: Mapped[str] = mapped_column(Text, primary_key=True)
    status_code: Mapped[int] = mapped_column(Integer, nullable=False)
    response: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = _created()
