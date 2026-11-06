from __future__ import annotations

import asyncio
import base64
import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from dcs_vault import KeyUnavailableError, LocalKeyService, Vault, VaultError, VaultIntegrityError, alias_for

T1 = "t_aaaaaaaaa1"


async def test_create_key_is_idempotent(local_keys: LocalKeyService) -> None:
    a = await local_keys.create_key(T1)
    b = await local_keys.create_key(T1)
    assert a == b
    assert a.startswith("local:")


async def test_concurrent_create_yields_one_key(local_keys: LocalKeyService) -> None:
    refs = await asyncio.gather(*(local_keys.create_key(T1) for _ in range(10)))
    assert len(set(refs)) == 1


async def test_key_file_contains_no_plaintext_kek(local_keys: LocalKeyService, tmp_path: Path) -> None:
    ref = await local_keys.create_key(T1)
    doc = json.loads((tmp_path / "keys" / f"{ref.removeprefix('local:')}.json").read_text())
    assert doc["alias"] == alias_for(T1)
    assert set(doc["versions"][0]) == {"version", "nonce", "wrapped"}


async def test_wrong_master_key_fails_authentication(tmp_path: Path) -> None:
    ks = LocalKeyService(os.urandom(32), tmp_path)
    ref = await ks.create_key(T1)
    other = LocalKeyService(os.urandom(32), tmp_path)
    with pytest.raises(VaultIntegrityError):
        await other.generate_data_key(ref, {})


async def test_schedule_deletion_blocks_use_and_purge_shreds(local_keys: LocalKeyService) -> None:
    vault = Vault(local_keys)
    tkey = await vault.new_tenant_key(T1)
    when = await local_keys.schedule_key_deletion(tkey.key_ref, 7)
    assert when > datetime.now(UTC) + timedelta(days=6)
    # idempotent: second call returns the same date
    assert await local_keys.schedule_key_deletion(tkey.key_ref, 30) == when
    state = await local_keys.describe(tkey.key_ref)
    assert state.status == "pending_deletion"
    assert state.deletion_date == when
    vault.forget()
    with pytest.raises(KeyUnavailableError):
        await local_keys.decrypt_data_key(tkey.key_ref, tkey.wrapped_dek, tkey.context())
    with pytest.raises(KeyUnavailableError):
        await local_keys.generate_data_key(tkey.key_ref, {})

    assert await local_keys.purge_due() == []  # not due yet
    purged = await local_keys.purge_due(now=when + timedelta(seconds=1))
    assert purged == [tkey.key_ref]
    assert (await local_keys.describe(tkey.key_ref)).status == "missing"
    with pytest.raises(KeyUnavailableError):
        await local_keys.decrypt_data_key(tkey.key_ref, tkey.wrapped_dek, tkey.context())


async def test_cancel_deletion(local_keys: LocalKeyService) -> None:
    ref = await local_keys.create_key(T1)
    await local_keys.schedule_key_deletion(ref, 7)
    await local_keys.cancel_key_deletion(ref)
    state = await local_keys.describe(ref)
    assert state.status == "enabled"
    assert state.deletion_date is None


@pytest.mark.parametrize("days", [0, 6, 31])
async def test_deletion_window_bounds(local_keys: LocalKeyService, days: int) -> None:
    ref = await local_keys.create_key(T1)
    with pytest.raises(ValueError, match="7-30"):
        await local_keys.schedule_key_deletion(ref, days)


async def test_truncated_and_unknown_version_wrapped_dek(local_keys: LocalKeyService) -> None:
    ref = await local_keys.create_key(T1)
    dk = await local_keys.generate_data_key(ref, {})
    with pytest.raises(VaultIntegrityError, match="truncated"):
        await local_keys.decrypt_data_key(ref, dk.wrapped[:10], {})
    with pytest.raises(VaultIntegrityError, match="unknown key version"):
        await local_keys.decrypt_data_key(ref, bytes([9]) + dk.wrapped[1:], {})


async def test_bad_key_refs(local_keys: LocalKeyService) -> None:
    with pytest.raises(VaultError, match="not a local key reference"):
        await local_keys.generate_data_key("arn:aws:kms:x", {})
    with pytest.raises(VaultError, match="malformed"):
        await local_keys.generate_data_key("local:../../etc", {})
    with pytest.raises(KeyUnavailableError):
        await local_keys.generate_data_key("local:deadbeef", {})


def test_master_key_validation(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="32 bytes"):
        LocalKeyService(b"short", tmp_path)
    with pytest.raises(ValueError, match="base64"):
        LocalKeyService.from_b64("not base64!!", tmp_path)
    ks = LocalKeyService.from_b64(base64.b64encode(os.urandom(32)).decode(), tmp_path)
    assert isinstance(ks, LocalKeyService)
