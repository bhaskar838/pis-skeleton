"""AwsKmsKeyService against moto's in-process KMS mock (no network)."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import boto3
import pytest
from moto import mock_aws

from dcs_vault import AwsKmsKeyService, KeyUnavailableError, Vault, VaultIntegrityError, build_aad

T1 = "t_aaaaaaaaa1"


@pytest.fixture
def kms() -> Iterator[Any]:
    with mock_aws():
        yield boto3.client("kms", region_name="ap-south-1")


async def test_create_key_alias_rotation_and_idempotency(kms: Any) -> None:
    ks = AwsKmsKeyService(kms)
    arn = await ks.create_key(T1)
    assert arn.startswith("arn:aws:kms:ap-south-1:")
    assert await ks.create_key(T1) == arn
    aliases = [a["AliasName"] for a in kms.list_aliases()["Aliases"]]
    assert f"alias/dcs/t/{T1}" in aliases
    assert kms.get_key_rotation_status(KeyId=arn)["KeyRotationEnabled"] is True


async def test_envelope_roundtrip_and_context_binding(kms: Any) -> None:
    ks = AwsKmsKeyService(kms)
    vault = Vault(ks)
    tkey = await vault.new_tenant_key(T1)
    aad = build_aad(T1, "credential", "c1")
    sealed = await vault.seal(tkey, b"kms-secret", aad)
    vault.forget()
    assert await vault.open(tkey, sealed) == b"kms-secret"
    with pytest.raises(VaultIntegrityError):
        await ks.decrypt_data_key(tkey.key_ref, tkey.wrapped_dek, {"dcs:tenant_id": "t_other00000"})


async def test_schedule_deletion_and_describe(kms: Any) -> None:
    ks = AwsKmsKeyService(kms)
    arn = await ks.create_key(T1)
    assert (await ks.describe(arn)).status == "enabled"
    when = await ks.schedule_key_deletion(arn, 7)
    assert when is not None
    # moto re-schedules (real KMS raises KMSInvalidStateException, covered by the stubbed test below)
    again = await ks.schedule_key_deletion(arn, 7)
    assert abs((again - when).total_seconds()) < 5
    state = await ks.describe(arn)
    assert state.status == "pending_deletion"


async def test_missing_key(kms: Any) -> None:
    ks = AwsKmsKeyService(kms)
    missing = "arn:aws:kms:ap-south-1:123456789012:key/00000000-0000-0000-0000-000000000000"
    assert (await ks.describe(missing)).status == "missing"
    with pytest.raises(KeyUnavailableError):
        await ks.generate_data_key(missing, {})


async def test_deletion_window_validated(kms: Any) -> None:
    ks = AwsKmsKeyService(kms)
    arn = await ks.create_key(T1)
    with pytest.raises(ValueError, match="7-30"):
        await ks.schedule_key_deletion(arn, 3)


async def test_real_kms_already_pending_returns_existing_date() -> None:
    """Real KMS raises KMSInvalidStateException when a key is already pending deletion."""
    from datetime import UTC, datetime

    from botocore.stub import Stubber

    client = boto3.client("kms", region_name="ap-south-1", aws_access_key_id="x", aws_secret_access_key="x")
    arn = "arn:aws:kms:ap-south-1:123456789012:key/11111111-1111-1111-1111-111111111111"
    deletion = datetime(2026, 12, 1, tzinfo=UTC)
    with Stubber(client) as stub:
        stub.add_client_error("schedule_key_deletion", service_error_code="KMSInvalidStateException")
        stub.add_response(
            "describe_key",
            {
                "KeyMetadata": {
                    "KeyId": "k",
                    "Arn": arn,
                    "KeyState": "PendingDeletion",
                    "DeletionDate": deletion,
                }
            },
            {"KeyId": arn},
        )
        assert await AwsKmsKeyService(client).schedule_key_deletion(arn, 7) == deletion

        stub.add_client_error("schedule_key_deletion", service_error_code="KMSInvalidStateException")
        stub.add_response(
            "describe_key",
            {"KeyMetadata": {"KeyId": "k", "Arn": arn, "KeyState": "Disabled"}},
            {"KeyId": arn},
        )
        with pytest.raises(client.exceptions.KMSInvalidStateException):
            await AwsKmsKeyService(client).schedule_key_deletion(arn, 7)

        stub.add_response(
            "describe_key",
            {"KeyMetadata": {"KeyId": "k", "Arn": arn, "KeyState": "Disabled"}},
            {"KeyId": arn},
        )
        assert (await AwsKmsKeyService(client).describe(arn)).status == "missing"


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        ("DisabledException", KeyUnavailableError),
        ("KMSInvalidStateException", KeyUnavailableError),
        ("NotFoundException", KeyUnavailableError),
        ("InvalidCiphertextException", VaultIntegrityError),
        ("IncorrectKeyException", VaultIntegrityError),
    ],
)
async def test_decrypt_error_mapping(code: str, expected: type[Exception]) -> None:
    from botocore.stub import Stubber

    client = boto3.client("kms", region_name="ap-south-1", aws_access_key_id="x", aws_secret_access_key="x")
    with Stubber(client) as stub:
        stub.add_client_error("decrypt", service_error_code=code)
        with pytest.raises(expected):
            await AwsKmsKeyService(client).decrypt_data_key("arn:aws:kms:x:1:key/k", b"wrapped", {})


@pytest.mark.parametrize("code", ["DisabledException", "KMSInvalidStateException", "NotFoundException"])
async def test_generate_error_mapping(code: str) -> None:
    from botocore.stub import Stubber

    client = boto3.client("kms", region_name="ap-south-1", aws_access_key_id="x", aws_secret_access_key="x")
    with Stubber(client) as stub:
        stub.add_client_error("generate_data_key", service_error_code=code)
        with pytest.raises(KeyUnavailableError):
            await AwsKmsKeyService(client).generate_data_key("arn:aws:kms:x:1:key/k", {})


def test_from_region() -> None:
    with mock_aws():
        assert isinstance(AwsKmsKeyService.from_region("eu-west-2"), AwsKmsKeyService)
