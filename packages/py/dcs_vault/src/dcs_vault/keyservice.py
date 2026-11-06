"""Key services: wrap / unwrap tenant data keys with a per-tenant key-encryption key (KEK).

* :class:`LocalKeyService` — dev/CI. One random KEK per tenant, stored in a key directory and itself wrapped
  by a master key. Deleting the key file is a real crypto-shred.
* :class:`AwsKmsKeyService` — prod. One customer-managed KMS key per tenant, ``alias/dcs/t/<tenant_id>``,
  with automatic rotation. Wrapped DEKs are bound to an encryption context.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import os
import secrets
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, Protocol

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from dcs_vault.errors import KeyUnavailableError, VaultError, VaultIntegrityError

if TYPE_CHECKING:
    from mypy_boto3_kms import KMSClient

KeyStatus = Literal["enabled", "pending_deletion", "missing"]
MIN_DELETION_DAYS = 7
MAX_DELETION_DAYS = 30


@dataclass(frozen=True)
class DataKey:
    plaintext: bytes
    wrapped: bytes


@dataclass(frozen=True)
class KeyState:
    key_ref: str
    status: KeyStatus
    deletion_date: datetime | None = None


def alias_for(tenant_id: str) -> str:
    return f"alias/dcs/t/{tenant_id}"


def _context_bytes(context: Mapping[str, str]) -> bytes:
    return json.dumps(dict(context), sort_keys=True, separators=(",", ":")).encode()


def _check_days(days: int) -> None:
    if not MIN_DELETION_DAYS <= days <= MAX_DELETION_DAYS:
        raise ValueError(f"pending deletion window must be {MIN_DELETION_DAYS}-{MAX_DELETION_DAYS} days")


class KeyService(Protocol):
    async def create_key(self, tenant_id: str) -> str:
        """Create (or return the existing) tenant KEK and return its key reference. Idempotent."""
        ...

    async def generate_data_key(self, key_ref: str, context: Mapping[str, str]) -> DataKey: ...

    async def decrypt_data_key(self, key_ref: str, wrapped: bytes, context: Mapping[str, str]) -> bytes: ...

    async def schedule_key_deletion(self, key_ref: str, pending_days: int) -> datetime: ...

    async def describe(self, key_ref: str) -> KeyState: ...


# --------------------------------------------------------------------------------------------- local
class LocalKeyService:
    """File-backed KEKs for development. Safe for concurrent processes sharing the key directory."""

    PREFIX = "local:"

    def __init__(self, master_key: bytes, key_dir: Path) -> None:
        if len(master_key) != 32:
            raise ValueError("local master key must be exactly 32 bytes")
        self._master = AESGCM(master_key)
        self._dir = key_dir
        self._dir.mkdir(parents=True, exist_ok=True)

    @classmethod
    def from_b64(cls, master_key_b64: str, key_dir: Path) -> LocalKeyService:
        try:
            raw = base64.b64decode(master_key_b64, validate=True)
        except ValueError as exc:
            raise ValueError("local master key must be base64") from exc
        return cls(raw, key_dir)

    # -- file helpers
    def _key_id(self, tenant_id: str) -> str:
        return hashlib.sha256(alias_for(tenant_id).encode()).hexdigest()[:32]

    def _path(self, key_id: str) -> Path:
        if not key_id.isalnum():
            raise VaultError("malformed key reference")
        return self._dir / f"{key_id}.json"

    def _parse_ref(self, key_ref: str) -> str:
        if not key_ref.startswith(self.PREFIX):
            raise VaultError("not a local key reference")
        return key_ref[len(self.PREFIX) :]

    def _read(self, key_id: str) -> dict[str, Any]:
        try:
            data: dict[str, Any] = json.loads(self._path(key_id).read_text(encoding="utf-8"))
        except FileNotFoundError:
            raise KeyUnavailableError("tenant key not found") from None
        return data

    def _write(self, key_id: str, doc: dict[str, Any]) -> None:
        tmp = self._path(key_id).with_suffix(f".{secrets.token_hex(4)}.tmp")
        tmp.write_text(json.dumps(doc), encoding="utf-8")
        os.replace(tmp, self._path(key_id))

    def _wrap_kek(self, key_id: str, version: int, kek: bytes) -> dict[str, Any]:
        nonce = os.urandom(12)
        aad = f"{key_id}:{version}".encode()
        return {
            "version": version,
            "nonce": base64.b64encode(nonce).decode(),
            "wrapped": base64.b64encode(self._master.encrypt(nonce, kek, aad)).decode(),
        }

    def _unwrap_kek(self, key_id: str, entry: Mapping[str, Any]) -> bytes:
        aad = f"{key_id}:{entry['version']}".encode()
        try:
            return self._master.decrypt(
                base64.b64decode(entry["nonce"]), base64.b64decode(entry["wrapped"]), aad
            )
        except InvalidTag:
            raise VaultIntegrityError(
                "key file failed authentication (wrong master key or tampered)"
            ) from None

    def _usable(self, key_id: str) -> dict[str, Any]:
        doc = self._read(key_id)
        if doc["state"] != "enabled":
            raise KeyUnavailableError("tenant key is scheduled for deletion")
        return doc

    # -- KeyService
    async def create_key(self, tenant_id: str) -> str:
        key_id = self._key_id(tenant_id)
        doc = {
            "key_id": key_id,
            "alias": alias_for(tenant_id),
            "state": "enabled",
            "created_at": datetime.now(UTC).isoformat(),
            "deletion_date": None,
            "versions": [self._wrap_kek(key_id, 1, os.urandom(32))],
        }
        try:
            fd = os.open(self._path(key_id), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            return self.PREFIX + key_id  # idempotent: same alias → same key
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(json.dumps(doc))
        return self.PREFIX + key_id

    async def rotate_key(self, key_ref: str) -> int:
        """Add a new KEK version (like KMS automatic rotation). Old wrapped DEKs still decrypt."""
        key_id = self._parse_ref(key_ref)
        doc = self._usable(key_id)
        version = max(v["version"] for v in doc["versions"]) + 1
        doc["versions"].append(self._wrap_kek(key_id, version, os.urandom(32)))
        self._write(key_id, doc)
        return int(version)

    async def generate_data_key(self, key_ref: str, context: Mapping[str, str]) -> DataKey:
        key_id = self._parse_ref(key_ref)
        doc = self._usable(key_id)
        entry = max(doc["versions"], key=lambda v: v["version"])
        kek = self._unwrap_kek(key_id, entry)
        dek = os.urandom(32)
        nonce = os.urandom(12)
        aad = key_id.encode() + b"|" + _context_bytes(context)
        wrapped = bytes([entry["version"]]) + nonce + AESGCM(kek).encrypt(nonce, dek, aad)
        return DataKey(plaintext=dek, wrapped=wrapped)

    async def decrypt_data_key(self, key_ref: str, wrapped: bytes, context: Mapping[str, str]) -> bytes:
        key_id = self._parse_ref(key_ref)
        doc = self._usable(key_id)
        if len(wrapped) < 1 + 12 + 16:
            raise VaultIntegrityError("wrapped data key is truncated")
        version, nonce, body = wrapped[0], wrapped[1:13], wrapped[13:]
        entry = next((v for v in doc["versions"] if v["version"] == version), None)
        if entry is None:
            raise VaultIntegrityError("wrapped data key references an unknown key version")
        kek = self._unwrap_kek(key_id, entry)
        aad = key_id.encode() + b"|" + _context_bytes(context)
        try:
            return AESGCM(kek).decrypt(nonce, body, aad)
        except InvalidTag:
            raise VaultIntegrityError("wrapped data key failed authentication") from None

    async def schedule_key_deletion(self, key_ref: str, pending_days: int) -> datetime:
        _check_days(pending_days)
        key_id = self._parse_ref(key_ref)
        doc = self._read(key_id)
        if doc["state"] == "pending_deletion":
            return datetime.fromisoformat(doc["deletion_date"])
        when = datetime.now(UTC) + timedelta(days=pending_days)
        doc["state"] = "pending_deletion"
        doc["deletion_date"] = when.isoformat()
        self._write(key_id, doc)
        return when

    async def cancel_key_deletion(self, key_ref: str) -> None:
        key_id = self._parse_ref(key_ref)
        doc = self._read(key_id)
        doc["state"] = "enabled"
        doc["deletion_date"] = None
        self._write(key_id, doc)

    async def describe(self, key_ref: str) -> KeyState:
        key_id = self._parse_ref(key_ref)
        try:
            doc = self._read(key_id)
        except KeyUnavailableError:
            return KeyState(key_ref, "missing")
        deletion = datetime.fromisoformat(doc["deletion_date"]) if doc["deletion_date"] else None
        return KeyState(key_ref, doc["state"], deletion)

    async def purge_due(self, now: datetime | None = None) -> list[str]:
        """Delete key files whose deletion date has passed (crypto-shred). Returns purged key refs."""
        now = now or datetime.now(UTC)
        purged: list[str] = []
        for path in self._dir.glob("*.json"):
            doc = json.loads(path.read_text(encoding="utf-8"))
            if doc["state"] == "pending_deletion" and datetime.fromisoformat(doc["deletion_date"]) <= now:
                path.unlink(missing_ok=True)
                purged.append(self.PREFIX + doc["key_id"])
        return purged


# ----------------------------------------------------------------------------------------------- AWS
class AwsKmsKeyService:
    """One customer-managed KMS key per tenant. boto3 calls run in a worker thread."""

    def __init__(self, client: KMSClient) -> None:
        self._kms = client

    @classmethod
    def from_region(cls, region: str) -> AwsKmsKeyService:
        import boto3

        return cls(boto3.client("kms", region_name=region))

    async def create_key(self, tenant_id: str) -> str:
        alias = alias_for(tenant_id)

        def _create() -> str:
            try:
                existing = self._kms.describe_key(KeyId=alias)
                return existing["KeyMetadata"]["Arn"]
            except self._kms.exceptions.NotFoundException:
                pass
            meta = self._kms.create_key(
                Description=f"DCS-PIS tenant key {tenant_id}",
                KeyUsage="ENCRYPT_DECRYPT",
                KeySpec="SYMMETRIC_DEFAULT",
                Tags=[{"TagKey": "dcs:tenant_id", "TagValue": tenant_id}],
            )["KeyMetadata"]
            self._kms.create_alias(AliasName=alias, TargetKeyId=meta["KeyId"])
            self._kms.enable_key_rotation(KeyId=meta["KeyId"])
            return meta["Arn"]

        return await asyncio.to_thread(_create)

    async def generate_data_key(self, key_ref: str, context: Mapping[str, str]) -> DataKey:
        def _gen() -> DataKey:
            try:
                out = self._kms.generate_data_key(
                    KeyId=key_ref, KeySpec="AES_256", EncryptionContext=dict(context)
                )
            except (self._kms.exceptions.DisabledException, self._kms.exceptions.KMSInvalidStateException):
                raise KeyUnavailableError("tenant key is disabled or pending deletion") from None
            except self._kms.exceptions.NotFoundException:
                raise KeyUnavailableError("tenant key not found") from None
            return DataKey(plaintext=out["Plaintext"], wrapped=out["CiphertextBlob"])

        return await asyncio.to_thread(_gen)

    async def decrypt_data_key(self, key_ref: str, wrapped: bytes, context: Mapping[str, str]) -> bytes:
        def _dec() -> bytes:
            try:
                out = self._kms.decrypt(
                    CiphertextBlob=wrapped, KeyId=key_ref, EncryptionContext=dict(context)
                )
            except (
                self._kms.exceptions.InvalidCiphertextException,
                self._kms.exceptions.IncorrectKeyException,
            ):
                raise VaultIntegrityError("wrapped data key failed authentication") from None
            except (self._kms.exceptions.DisabledException, self._kms.exceptions.KMSInvalidStateException):
                raise KeyUnavailableError("tenant key is disabled or pending deletion") from None
            except self._kms.exceptions.NotFoundException:
                raise KeyUnavailableError("tenant key not found") from None
            return out["Plaintext"]

        return await asyncio.to_thread(_dec)

    async def schedule_key_deletion(self, key_ref: str, pending_days: int) -> datetime:
        _check_days(pending_days)

        # KMS accepts an ARN or a bare key ID here; the bare ID also works with moto in tests.
        key_id = key_ref.rsplit("key/", 1)[-1] if key_ref.startswith("arn:") else key_ref

        def _sched() -> datetime:
            try:
                out = self._kms.schedule_key_deletion(KeyId=key_id, PendingWindowInDays=pending_days)
                return out["DeletionDate"]
            except self._kms.exceptions.KMSInvalidStateException:
                meta = self._kms.describe_key(KeyId=key_ref)["KeyMetadata"]
                deletion = meta.get("DeletionDate")
                if deletion is None:
                    raise
                return deletion

        return await asyncio.to_thread(_sched)

    async def describe(self, key_ref: str) -> KeyState:
        def _desc() -> KeyState:
            try:
                meta = self._kms.describe_key(KeyId=key_ref)["KeyMetadata"]
            except self._kms.exceptions.NotFoundException:
                return KeyState(key_ref, "missing")
            if meta["KeyState"] == "PendingDeletion":
                return KeyState(key_ref, "pending_deletion", meta.get("DeletionDate"))
            if meta["KeyState"] == "Enabled":
                return KeyState(key_ref, "enabled")
            return KeyState(key_ref, "missing")

        return await asyncio.to_thread(_desc)
