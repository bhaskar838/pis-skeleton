"""Vault encrypt / decrypt / rotate / tamper tests (SPEC §13 P0, P0-T8)."""

from __future__ import annotations

import dataclasses

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from dcs_vault import (
    LocalKeyService,
    Sealed,
    TenantKey,
    Vault,
    VaultIntegrityError,
    WrongKeyError,
    build_aad,
    dek_fingerprint,
)

T1 = "t_aaaaaaaaa1"
T2 = "t_bbbbbbbbb2"
AAD = build_aad(T1, "credential", "cred-1")


def _flip(b: bytes, index: int) -> bytes:
    arr = bytearray(b)
    arr[index] ^= 0x01
    return bytes(arr)


async def test_roundtrip(vault: Vault) -> None:
    tkey = await vault.new_tenant_key(T1)
    sealed = await vault.seal(tkey, b"s3cr3t-password", AAD)
    assert b"s3cr3t" not in sealed.ciphertext
    assert sealed.aad == AAD
    assert await vault.open(tkey, sealed) == b"s3cr3t-password"


async def test_roundtrip_without_cache(vault: Vault) -> None:
    tkey = await vault.new_tenant_key(T1)
    sealed = await vault.seal(tkey, b"x", AAD)
    vault.forget()
    assert await vault.open(tkey, sealed) == b"x"


async def test_cache_expiry_refetches(local_keys: LocalKeyService) -> None:
    v = Vault(local_keys, cache_ttl_s=-1)  # always expired
    tkey = await v.new_tenant_key(T1)
    assert await v.open(tkey, await v.seal(tkey, b"y", AAD)) == b"y"


async def test_nonces_are_unique(vault: Vault) -> None:
    tkey = await vault.new_tenant_key(T1)
    nonces = {(await vault.seal(tkey, b"same", AAD)).nonce for _ in range(50)}
    assert len(nonces) == 50


@settings(max_examples=25, deadline=None)
@given(payload=st.binary(max_size=4096))
async def test_roundtrip_property(payload: bytes) -> None:
    import os
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as d:
        v = Vault(LocalKeyService(os.urandom(32), Path(d)))
        tkey = await v.new_tenant_key(T1)
        assert await v.open(tkey, await v.seal(tkey, payload, AAD)) == payload


# ----------------------------------------------------------------------------- tamper (AAD binding)
async def test_tampered_aad_is_rejected(vault: Vault) -> None:
    tkey = await vault.new_tenant_key(T1)
    sealed = await vault.seal(tkey, b"p", AAD)
    moved = dataclasses.replace(sealed, aad=build_aad(T1, "credential", "cred-2"))
    with pytest.raises(VaultIntegrityError):
        await vault.open(tkey, moved)


@pytest.mark.parametrize("index", [10, 15, -1])  # inside body, mid, last byte of the tag
async def test_ciphertext_bit_flip_is_rejected(vault: Vault, index: int) -> None:
    tkey = await vault.new_tenant_key(T1)
    sealed = await vault.seal(tkey, b"payload-bytes", AAD)
    with pytest.raises(VaultIntegrityError):
        await vault.open(tkey, dataclasses.replace(sealed, ciphertext=_flip(sealed.ciphertext, index)))


async def test_nonce_tamper_is_rejected(vault: Vault) -> None:
    tkey = await vault.new_tenant_key(T1)
    sealed = await vault.seal(tkey, b"p", AAD)
    with pytest.raises(VaultIntegrityError):
        await vault.open(tkey, dataclasses.replace(sealed, nonce=_flip(sealed.nonce, 0)))


async def test_wrong_nonce_length_is_rejected(vault: Vault) -> None:
    tkey = await vault.new_tenant_key(T1)
    sealed = await vault.seal(tkey, b"p", AAD)
    with pytest.raises(VaultIntegrityError):
        await vault.open(tkey, dataclasses.replace(sealed, nonce=sealed.nonce[:8]))


@pytest.mark.parametrize("ct", [b"", b"v1", b"v2" + b"\x00" * 40, b"v1" + b"\x00" * 10])
async def test_malformed_ciphertext_is_rejected(vault: Vault, ct: bytes) -> None:
    tkey = await vault.new_tenant_key(T1)
    with pytest.raises(VaultIntegrityError):
        await vault.open(tkey, Sealed(ciphertext=ct, nonce=b"\x00" * 12, aad=AAD))


async def test_other_tenant_key_cannot_open(vault: Vault) -> None:
    k1 = await vault.new_tenant_key(T1)
    k2 = await vault.new_tenant_key(T2)
    sealed = await vault.seal(k1, b"tenant-1-secret", AAD)
    with pytest.raises(WrongKeyError):
        await vault.open(k2, sealed)


async def test_same_dek_but_other_tenant_label_fails_aad(vault: Vault) -> None:
    """Even with identical key material, the tenant id is bound into the GCM AAD."""
    k1 = await vault.new_tenant_key(T1)
    sealed = await vault.seal(k1, b"x", AAD)
    forged = TenantKey(T2, k1.key_ref, k1.wrapped_dek)
    vault._cache[(T2, forged.dek_id)] = vault._cache[(T1, k1.dek_id)]  # simulate identical DEK
    with pytest.raises(VaultIntegrityError):
        await vault.open(forged, sealed)


async def test_tampered_wrapped_dek_is_rejected(vault: Vault) -> None:
    tkey = await vault.new_tenant_key(T1)
    sealed = await vault.seal(tkey, b"x", AAD)
    vault.forget()
    bad = TenantKey(T1, tkey.key_ref, _flip(tkey.wrapped_dek, 20))
    # dek_id changes with the wrapped DEK, so the vault reports the mismatch before unwrapping
    with pytest.raises(WrongKeyError):
        await vault.open(bad, sealed)
    with pytest.raises(VaultIntegrityError):
        await vault.seal(bad, b"y", AAD)


async def test_wrapped_dek_is_bound_to_tenant_context(vault: Vault, local_keys: LocalKeyService) -> None:
    tkey = await vault.new_tenant_key(T1)
    with pytest.raises(VaultIntegrityError):
        await local_keys.decrypt_data_key(tkey.key_ref, tkey.wrapped_dek, {"dcs:tenant_id": T2})


# ---------------------------------------------------------------------------------------- rotation
async def test_rotate_dek_and_reseal(vault: Vault) -> None:
    old = await vault.new_tenant_key(T1)
    sealed = await vault.seal(old, b"rotate-me", AAD)
    new = await vault.rotate_dek(old)
    assert new.wrapped_dek != old.wrapped_dek
    assert new.dek_id != old.dek_id
    with pytest.raises(WrongKeyError):
        await vault.open(new, sealed)
    resealed = await vault.reseal(old, new, sealed)
    vault.forget(T1)
    assert await vault.open(new, resealed) == b"rotate-me"


async def test_reseal_across_tenants_is_refused(vault: Vault) -> None:
    k1 = await vault.new_tenant_key(T1)
    k2 = await vault.new_tenant_key(T2)
    with pytest.raises(ValueError, match="across tenants"):
        await vault.reseal(k1, k2, await vault.seal(k1, b"x", AAD))


async def test_kek_rotation_keeps_old_wrapped_deks_usable(vault: Vault, local_keys: LocalKeyService) -> None:
    tkey = await vault.new_tenant_key(T1)
    sealed = await vault.seal(tkey, b"before", AAD)
    assert await local_keys.rotate_key(tkey.key_ref) == 2
    vault.forget()
    assert await vault.open(tkey, sealed) == b"before"
    newer = await vault.rotate_dek(tkey)  # wrapped under KEK v2
    assert newer.wrapped_dek[0] == 2
    vault.forget()
    assert await vault.open(newer, await vault.seal(newer, b"after", AAD)) == b"after"


def test_forget_one_tenant(vault: Vault) -> None:
    vault._cache[(T1, b"1")] = (b"k", 1e18)
    vault._cache[(T2, b"2")] = (b"k", 1e18)
    vault.forget(T1)
    assert list(vault._cache) == [(T2, b"2")]


def test_key_service_property(vault: Vault, local_keys: LocalKeyService) -> None:
    assert vault.key_service is local_keys


# ------------------------------------------------------------------------------------------- helpers
@pytest.mark.parametrize(
    ("args", "ok"),
    [
        ((T1, "credential", "c1"), True),
        (("", "p", "r"), False),
        ((T1, "a:b", "r"), False),
        ((T1, "p", "r|x"), False),
    ],
)
def test_build_aad(args: tuple[str, str, str], ok: bool) -> None:
    if ok:
        assert build_aad(*args) == f"dcs:v1:{args[0]}:{args[1]}:{args[2]}"
    else:
        with pytest.raises(ValueError, match="AAD"):
            build_aad(*args)


def test_dek_fingerprint_is_stable() -> None:
    assert dek_fingerprint(b"abc") == dek_fingerprint(b"abc")
    assert len(dek_fingerprint(b"abc")) == 8
