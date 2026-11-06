"""Identifier helpers: UUIDv7, tenant short IDs, deterministic workflow IDs."""

from __future__ import annotations

import re
import secrets
import time
import uuid

_TENANT_ALPHABET = "abcdefghijklmnopqrstuvwxyz0123456789"
_TENANT_ID_RE = re.compile(r"^t_[a-z][a-z0-9]{9}$")
_WF_PART_RE = re.compile(r"^[A-Za-z0-9_.\-]+$")


def uuid7() -> uuid.UUID:
    """Return an RFC 9562 UUIDv7 (48-bit Unix ms timestamp + 74 random bits)."""
    ts_ms = time.time_ns() // 1_000_000
    raw = bytearray(ts_ms.to_bytes(6, "big") + secrets.token_bytes(10))
    raw[6] = (raw[6] & 0x0F) | 0x70  # version 7
    raw[8] = (raw[8] & 0x3F) | 0x80  # RFC 4122 variant
    return uuid.UUID(bytes=bytes(raw))


def new_tenant_id() -> str:
    """Return a new tenant ID such as ``t_k3x9a0b2c4``.

    The tenant ID doubles as the tenant database name, so it is restricted to lowercase ASCII letters and
    digits, starts with a letter and has a fixed length (safe as a Postgres identifier).
    """
    first = secrets.choice(_TENANT_ALPHABET[:26])
    rest = "".join(secrets.choice(_TENANT_ALPHABET) for _ in range(9))
    return f"t_{first}{rest}"


def is_tenant_id(value: str) -> bool:
    return bool(_TENANT_ID_RE.fullmatch(value))


def workflow_id(kind: str, tenant: str, natural_key: str) -> str:
    """Deterministic Temporal workflow ID: ``wf:<kind>:<tenant>:<natural-key>`` (SPEC §12)."""
    for part in (kind, tenant, natural_key):
        if not _WF_PART_RE.fullmatch(part):
            raise ValueError(f"invalid workflow id component: {part!r}")
    return f"wf:{kind}:{tenant}:{natural_key}"
