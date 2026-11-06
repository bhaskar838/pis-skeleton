"""Envelope encryption library (SPEC §3.5, P0-T8)."""

from dcs_vault.envelope import Sealed, TenantKey, Vault, build_aad, dek_fingerprint
from dcs_vault.errors import KeyUnavailableError, VaultError, VaultIntegrityError, WrongKeyError
from dcs_vault.keyservice import (
    AwsKmsKeyService,
    DataKey,
    KeyService,
    KeyState,
    LocalKeyService,
    alias_for,
)

__all__ = [
    "AwsKmsKeyService",
    "DataKey",
    "KeyService",
    "KeyState",
    "KeyUnavailableError",
    "LocalKeyService",
    "Sealed",
    "TenantKey",
    "Vault",
    "VaultError",
    "VaultIntegrityError",
    "WrongKeyError",
    "alias_for",
    "build_aad",
    "dek_fingerprint",
]
