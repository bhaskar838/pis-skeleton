"""Audit hash chain (SPEC §2 P9, §8.5).

Storage-agnostic: the control-api persists events, this module defines the canonical payload, how each hash
is computed and how a chain is verified. Each org has its own chain; platform events (no org) use
:data:`PLATFORM_CHAIN`.

``hash = SHA-256(prev_hash || canonical_json(event fields))``

Verification detects modified fields, re-ordered rows and deleted rows in the middle of a chain. Deleting the
*tail* of a chain is detected with an anchor: the last verified ``(id, hash)`` pair, stored by each
verification run, must still be present and unchanged.
"""

from __future__ import annotations

import hashlib
import ipaddress
import json
import uuid
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

GENESIS_HASH = b"\x00" * 32
PLATFORM_CHAIN = uuid.UUID(int=0)

ActorType = str  # "user" | "staff" | "system" | "api_key"


def _normalise(value: Any) -> Any:
    if isinstance(value, datetime):
        return _iso(value)
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, Mapping):
        return {str(k): _normalise(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [_normalise(v) for v in value]
    if isinstance(value, bytes):
        return value.hex()
    return value


def _iso(ts: datetime) -> str:
    if ts.tzinfo is None:
        raise ValueError("audit timestamps must be timezone-aware")
    return ts.astimezone(UTC).isoformat(timespec="microseconds")


def normalise_ip(ip: str | None) -> str | None:
    if ip is None or ip == "":
        return None
    try:
        return str(ipaddress.ip_address(ip.split("/")[0]))
    except ValueError:
        return None


@dataclass(frozen=True)
class AuditFields:
    """The hashed content of one audit event (everything except ``id``, ``prev_hash`` and ``hash``)."""

    ts: datetime
    org_id: uuid.UUID | None
    actor_type: ActorType
    actor_id: str | None
    action: str
    target_type: str | None = None
    target_id: str | None = None
    ip: str | None = None
    ua: str | None = None
    details: Mapping[str, Any] = field(default_factory=dict)

    def canonical(self) -> bytes:
        body = {
            "ts": _iso(self.ts),
            "org_id": str(self.org_id) if self.org_id else None,
            "actor_type": self.actor_type,
            "actor_id": self.actor_id,
            "action": self.action,
            "target_type": self.target_type,
            "target_id": self.target_id,
            "ip": normalise_ip(self.ip),
            "ua": self.ua,
            "details": _normalise(dict(self.details)),
        }
        return json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def compute_hash(prev_hash: bytes, fields: AuditFields) -> bytes:
    if len(prev_hash) != 32:
        raise ValueError("prev_hash must be 32 bytes")
    return hashlib.sha256(prev_hash + fields.canonical()).digest()


@dataclass(frozen=True)
class StoredAuditEvent:
    id: int
    fields: AuditFields
    prev_hash: bytes
    hash: bytes


@dataclass(frozen=True)
class Anchor:
    event_id: int
    hash: bytes


@dataclass(frozen=True)
class ChainVerification:
    ok: bool
    checked: int
    last_id: int | None
    last_hash: bytes | None
    first_bad_id: int | None = None
    reason: str | None = None


def verify_chain(events: Iterable[StoredAuditEvent], anchor: Anchor | None = None) -> ChainVerification:
    """Verify one chain. ``events`` must be the complete chain in ascending ``id`` order."""
    expected_prev = GENESIS_HASH
    checked = 0
    last: StoredAuditEvent | None = None
    anchor_seen = anchor is None
    for ev in events:
        if last is not None and ev.id <= last.id:
            return ChainVerification(False, checked, last.id, last.hash, ev.id, "events out of order")
        if ev.prev_hash != expected_prev:
            return ChainVerification(
                False,
                checked,
                last.id if last else None,
                last.hash if last else None,
                ev.id,
                "prev_hash does not match the previous event (row deleted or re-ordered)",
            )
        recomputed = compute_hash(ev.prev_hash, ev.fields)
        if recomputed != ev.hash:
            return ChainVerification(
                False,
                checked,
                last.id if last else None,
                last.hash if last else None,
                ev.id,
                "hash mismatch (row modified)",
            )
        if anchor is not None and ev.id == anchor.event_id:
            if ev.hash != anchor.hash:
                return ChainVerification(False, checked, ev.id, ev.hash, ev.id, "anchor hash changed")
            anchor_seen = True
        expected_prev = ev.hash
        last = ev
        checked += 1
    if not anchor_seen:
        assert anchor is not None  # noqa: S101 - narrowed by anchor_seen
        return ChainVerification(
            False,
            checked,
            last.id if last else None,
            last.hash if last else None,
            anchor.event_id,
            "anchored event missing (tail truncated)",
        )
    return ChainVerification(True, checked, last.id if last else None, last.hash if last else None)
