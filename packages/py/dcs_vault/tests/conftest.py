from __future__ import annotations

import os
from pathlib import Path

import pytest

from dcs_vault import LocalKeyService, Vault


@pytest.fixture
def master_key() -> bytes:
    return os.urandom(32)


@pytest.fixture
def local_keys(tmp_path: Path, master_key: bytes) -> LocalKeyService:
    return LocalKeyService(master_key, tmp_path / "keys")


@pytest.fixture
def vault(local_keys: LocalKeyService) -> Vault:
    return Vault(local_keys)
