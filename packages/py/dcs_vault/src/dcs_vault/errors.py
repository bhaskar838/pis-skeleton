from __future__ import annotations


class VaultError(Exception):
    """Base class for vault errors. Messages never contain key material or plaintext."""


class VaultIntegrityError(VaultError):
    """Authentication failed: ciphertext, nonce, AAD or wrapped key was modified, or the wrong key was used."""


class KeyUnavailableError(VaultError):
    """The tenant key is missing, disabled or scheduled for deletion."""


class WrongKeyError(VaultError):
    """The sealed value was produced with a different data key than the one supplied."""
