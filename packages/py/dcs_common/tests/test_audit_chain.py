"""Audit hash-chain unit tests (SPEC §8.5, P0-T9)."""

from __future__ import annotations

import dataclasses
import uuid
from datetime import UTC, datetime, timedelta, timezone

import pytest

from dcs_common.audit import (
    GENESIS_HASH,
    Anchor,
    AuditFields,
    StoredAuditEvent,
    compute_hash,
    normalise_ip,
    verify_chain,
)

ORG = uuid.UUID("0193f0e2-7a1c-7c3e-9a51-2b6f1d9e4a10")
T0 = datetime(2026, 11, 6, 10, 0, tzinfo=UTC)


def _fields(i: int, **kw: object) -> AuditFields:
    base: dict[str, object] = {
        "ts": T0 + timedelta(seconds=i),
        "org_id": ORG,
        "actor_type": "user",
        "actor_id": "user-1",
        "action": f"test.action.{i}",
        "target_type": "org",
        "target_id": str(ORG),
        "ip": "10.0.0.1",
        "ua": "pytest",
        "details": {"n": i, "nested": {"b": 2, "a": [1, "x"]}},
    }
    base.update(kw)
    return AuditFields(**base)  # type: ignore[arg-type]


def _chain(n: int) -> list[StoredAuditEvent]:
    out: list[StoredAuditEvent] = []
    prev = GENESIS_HASH
    for i in range(n):
        f = _fields(i)
        h = compute_hash(prev, f)
        out.append(StoredAuditEvent(id=i + 1, fields=f, prev_hash=prev, hash=h))
        prev = h
    return out


def test_valid_chain_verifies() -> None:
    result = verify_chain(_chain(5))
    assert result.ok
    assert result.checked == 5
    assert result.last_id == 5
    assert result.first_bad_id is None


def test_empty_chain_is_valid() -> None:
    result = verify_chain([])
    assert result.ok
    assert result.checked == 0
    assert result.last_id is None


def test_modified_field_is_detected() -> None:
    chain = _chain(5)
    tampered = dataclasses.replace(chain[2].fields, details={"n": 999})
    chain[2] = dataclasses.replace(chain[2], fields=tampered)
    result = verify_chain(chain)
    assert not result.ok
    assert result.first_bad_id == 3
    assert result.reason is not None
    assert "modified" in result.reason


def test_deleted_middle_row_is_detected() -> None:
    chain = _chain(5)
    del chain[2]
    result = verify_chain(chain)
    assert not result.ok
    assert result.first_bad_id == 4


def test_reordered_rows_are_detected() -> None:
    chain = _chain(4)
    chain[1], chain[2] = chain[2], chain[1]
    assert not verify_chain(chain).ok


def test_out_of_order_ids_are_detected() -> None:
    chain = _chain(3)
    chain[2] = dataclasses.replace(chain[2], id=1)
    result = verify_chain(chain)
    assert not result.ok
    assert result.reason == "events out of order"


def test_recomputed_forgery_breaks_the_next_link() -> None:
    """An attacker who rewrites a row and recomputes its hash still breaks the following row's prev_hash."""
    chain = _chain(4)
    forged_fields = dataclasses.replace(chain[1].fields, action="forged")
    chain[1] = dataclasses.replace(
        chain[1], fields=forged_fields, hash=compute_hash(chain[1].prev_hash, forged_fields)
    )
    result = verify_chain(chain)
    assert not result.ok
    assert result.first_bad_id == 3


def test_tail_truncation_detected_with_anchor() -> None:
    chain = _chain(5)
    anchor = Anchor(event_id=5, hash=chain[4].hash)
    assert verify_chain(chain, anchor).ok
    result = verify_chain(chain[:3], anchor)
    assert not result.ok
    assert result.reason == "anchored event missing (tail truncated)"


def test_anchor_hash_change_detected() -> None:
    chain = _chain(3)
    result = verify_chain(chain, Anchor(event_id=2, hash=b"\x01" * 32))
    assert not result.ok
    assert result.reason == "anchor hash changed"


def test_canonical_form_is_independent_of_key_order_and_timezone() -> None:
    a = _fields(1, details={"x": 1, "y": {"b": 1, "a": 2}})
    b = _fields(
        1,
        details={"y": {"a": 2, "b": 1}, "x": 1},
        ts=(T0 + timedelta(seconds=1)).astimezone(timezone(timedelta(hours=5, minutes=30))),
    )
    assert a.canonical() == b.canonical()


def test_canonical_normalises_values() -> None:
    f = _fields(1, details={"u": uuid.UUID(int=1), "t": T0, "b": b"\x01", "l": (1, 2)}, ip="10.0.0.1/32")
    text = f.canonical().decode()
    assert '"ip":"10.0.0.1"' in text
    assert "00000000-0000-0000-0000-000000000001" in text
    assert '"b":"01"' in text


def test_naive_timestamp_rejected() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        _fields(1, ts=datetime(2026, 1, 1)).canonical()  # noqa: DTZ001


def test_prev_hash_length_checked() -> None:
    with pytest.raises(ValueError, match="32 bytes"):
        compute_hash(b"short", _fields(1))


@pytest.mark.parametrize(
    ("raw", "expected"),
    [(None, None), ("", None), ("bogus", None), ("::1", "::1"), ("192.168.1.5/32", "192.168.1.5")],
)
def test_normalise_ip(raw: str | None, expected: str | None) -> None:
    assert normalise_ip(raw) == expected


def test_platform_events_without_org() -> None:
    f = _fields(1, org_id=None)
    assert '"org_id":null' in f.canonical().decode()
