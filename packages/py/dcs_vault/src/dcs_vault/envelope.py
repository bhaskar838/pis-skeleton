"""Envelope encryption for tenant secrets (credentials, tenant DB role passwords, field-level encryption).

Layout of :attr:`Sealed.ciphertext`::

    b"v1" | dek_id (8 bytes) | AES-256-GCM(ciphertext || tag)

* ``dek_id`` = first 8 bytes of SHA-256(wrapped DEK). It lets :meth:`Vault.open` say *which* key a value was
  sealed with, which matters during DEK rotation.
* The GCM associated data is ``"<tenant_id>|<aad>"``, so a value cannot be moved to another tenant or another
  record (the caller's ``aad`` names the purpose and record, see :func:`build_aad`).
"""

from __future__ import annotations

import hashlib
import os
import time
from dataclasses import dataclass

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from dcs_vault.errors import VaultIntegrityError, WrongKeyError
from dcs_vault.keyservice import KeyService

FORMAT_V1 = b"v1"
NONCE_LEN = 12
DEK_ID_LEN = 8


def build_aad(tenant_id: str, purpose: str, record_id: str) -> str:
    """Canonical AAD string: ``dcs:v1:<tenant_id>:<purpose>:<record_id>``."""
    for part in (tenant_id, purpose, record_id):
        if not part or ":" in part or "|" in part:
            raise ValueError("AAD components must be non-empty and must not contain ':' or '|'")
    return f"dcs:v1:{tenant_id}:{purpose}:{record_id}"


def dek_fingerprint(wrapped_dek: bytes) -> bytes:
    return hashlib.sha256(wrapped_dek).digest()[:DEK_ID_LEN]


@dataclass(frozen=True)
class TenantKey:
    """The persisted key material for one tenant (row in ``tenant_key``). Never holds plaintext."""

    tenant_id: str
    key_ref: str
    wrapped_dek: bytes

    @property
    def dek_id(self) -> bytes:
        return dek_fingerprint(self.wrapped_dek)

    def context(self) -> dict[str, str]:
        return {"dcs:tenant_id": self.tenant_id, "dcs:purpose": "tenant-dek"}


@dataclass(frozen=True)
class Sealed:
    ciphertext: bytes
    nonce: bytes
    aad: str


class Vault:
    def __init__(self, keys: KeyService, *, cache_ttl_s: float = 300.0) -> None:
        self._keys = keys
        self._ttl = cache_ttl_s
        self._cache: dict[tuple[str, bytes], tuple[bytes, float]] = {}

    @property
    def key_service(self) -> KeyService:
        return self._keys

    async def new_tenant_key(self, tenant_id: str) -> TenantKey:
        key_ref = await self._keys.create_key(tenant_id)
        probe = TenantKey(tenant_id, key_ref, b"")
        dk = await self._keys.generate_data_key(key_ref, probe.context())
        tkey = TenantKey(tenant_id, key_ref, dk.wrapped)
        self._remember(tkey, dk.plaintext)
        return tkey

    async def rotate_dek(self, tkey: TenantKey) -> TenantKey:
        """Generate a new DEK under the same KEK. Callers must :meth:`reseal` existing values."""
        dk = await self._keys.generate_data_key(tkey.key_ref, tkey.context())
        new = TenantKey(tkey.tenant_id, tkey.key_ref, dk.wrapped)
        self._remember(new, dk.plaintext)
        return new

    async def seal(self, tkey: TenantKey, plaintext: bytes, aad: str) -> Sealed:
        dek = await self._dek(tkey)
        nonce = os.urandom(NONCE_LEN)
        body = AESGCM(dek).encrypt(nonce, plaintext, self._gcm_aad(tkey, aad))
        return Sealed(ciphertext=FORMAT_V1 + tkey.dek_id + body, nonce=nonce, aad=aad)

    async def open(self, tkey: TenantKey, sealed: Sealed) -> bytes:
        ct = sealed.ciphertext
        header_len = len(FORMAT_V1) + DEK_ID_LEN
        if len(ct) < header_len + 16 or ct[: len(FORMAT_V1)] != FORMAT_V1:
            raise VaultIntegrityError("sealed value is malformed or truncated")
        if len(sealed.nonce) != NONCE_LEN:
            raise VaultIntegrityError("nonce has the wrong length")
        if ct[len(FORMAT_V1) : header_len] != tkey.dek_id:
            raise WrongKeyError("value was sealed with a different data key")
        dek = await self._dek(tkey)
        try:
            return AESGCM(dek).decrypt(sealed.nonce, ct[header_len:], self._gcm_aad(tkey, sealed.aad))
        except InvalidTag:
            raise VaultIntegrityError("sealed value failed authentication") from None

    async def reseal(self, old: TenantKey, new: TenantKey, sealed: Sealed) -> Sealed:
        if old.tenant_id != new.tenant_id:
            raise ValueError("cannot reseal across tenants")
        return await self.seal(new, await self.open(old, sealed), sealed.aad)

    def forget(self, tenant_id: str | None = None) -> None:
        """Drop cached plaintext DEKs (all, or one tenant's)."""
        if tenant_id is None:
            self._cache.clear()
        else:
            for k in [k for k in self._cache if k[0] == tenant_id]:
                del self._cache[k]

    # ---------------------------------------------------------------- internals
    @staticmethod
    def _gcm_aad(tkey: TenantKey, aad: str) -> bytes:
        return f"{tkey.tenant_id}|{aad}".encode()

    def _remember(self, tkey: TenantKey, dek: bytes) -> None:
        self._cache[(tkey.tenant_id, tkey.dek_id)] = (dek, time.monotonic() + self._ttl)

    async def _dek(self, tkey: TenantKey) -> bytes:
        hit = self._cache.get((tkey.tenant_id, tkey.dek_id))
        if hit is not None and hit[1] > time.monotonic():
            return hit[0]
        dek = await self._keys.decrypt_data_key(tkey.key_ref, tkey.wrapped_dek, tkey.context())
        self._remember(tkey, dek)
        return dek
