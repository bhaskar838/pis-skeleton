"""Per-tenant object-store prefixes (SPEC §3.5, §8.1 step 5).

``s3://<bucket>/tenants/<tenant_id>/{landing,bronze,exports,browser-artifacts}/``

In prod every object is encrypted with the tenant CMK (SSE-KMS) and the bucket uses Object Lock (compliance) on
landing/bronze, so deprovisioning cannot delete those objects early: it tags them for the lifecycle rule
instead. In dev (MinIO, no lock) objects are deleted directly.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    from mypy_boto3_s3 import S3Client

ZONES = ("landing", "bronze", "exports", "browser-artifacts")
MARKER = ".dcs-prefix"


@dataclass(frozen=True)
class ObjectStoreConfig:
    bucket: str
    sse: Literal["none", "aws:kms"] = "none"
    object_lock_mode: Literal["none", "compliance"] = "none"


def tenant_prefix(tenant_id: str) -> str:
    return f"tenants/{tenant_id}/"


def build_client(endpoint: str | None, access_key: str, secret_key: str, region: str) -> S3Client:
    import boto3
    from botocore.config import Config

    kwargs: dict[str, Any] = {"region_name": region, "config": Config(s3={"addressing_style": "path"})}
    if endpoint:
        kwargs["endpoint_url"] = endpoint
    if access_key:
        kwargs["aws_access_key_id"] = access_key
        kwargs["aws_secret_access_key"] = secret_key
    return boto3.client("s3", **kwargs)


class TenantObjectStore:
    def __init__(self, client: S3Client, cfg: ObjectStoreConfig) -> None:
        self._s3 = client
        self._cfg = cfg

    async def create_prefixes(self, tenant_id: str, kms_key_arn: str | None) -> list[str]:
        def _put() -> list[str]:
            keys: list[str] = []
            for zone in ZONES:
                key = f"{tenant_prefix(tenant_id)}{zone}/{MARKER}"
                extra: dict[str, Any] = {"Metadata": {"dcs-tenant": tenant_id}}
                if self._cfg.sse == "aws:kms" and kms_key_arn:
                    extra.update({"ServerSideEncryption": "aws:kms", "SSEKMSKeyId": kms_key_arn})
                self._s3.put_object(Bucket=self._cfg.bucket, Key=key, Body=b"", **extra)
                keys.append(key)
            return keys

        return await asyncio.to_thread(_put)

    async def prefixes_present(self, tenant_id: str) -> list[str]:
        def _list() -> list[str]:
            out = self._s3.list_objects_v2(Bucket=self._cfg.bucket, Prefix=tenant_prefix(tenant_id))
            return sorted(o["Key"] for o in out.get("Contents", []))

        return await asyncio.to_thread(_list)

    async def delete_prefix(self, tenant_id: str) -> tuple[int, str]:
        """Returns (objects affected, mode) where mode is ``deleted`` or ``lifecycle-tagged``."""
        prefix = tenant_prefix(tenant_id)

        def _delete() -> tuple[int, str]:
            count = 0
            paginator = self._s3.get_paginator("list_object_versions")
            for page in paginator.paginate(Bucket=self._cfg.bucket, Prefix=prefix):
                versions = [*page.get("Versions", []), *page.get("DeleteMarkers", [])]
                if not versions:
                    continue
                if self._cfg.object_lock_mode == "compliance":
                    for v in page.get("Versions", []):
                        self._s3.put_object_tagging(
                            Bucket=self._cfg.bucket,
                            Key=v["Key"],
                            VersionId=v["VersionId"],
                            Tagging={"TagSet": [{"Key": "dcs-deprovisioned", "Value": "true"}]},
                        )
                        count += 1
                    continue
                objs = [{"Key": v["Key"], "VersionId": v["VersionId"]} for v in versions]
                for i in range(0, len(objs), 1000):
                    self._s3.delete_objects(Bucket=self._cfg.bucket, Delete={"Objects": objs[i : i + 1000]})  # type: ignore[typeddict-item]
                count += len(objs)
            if count == 0:  # unversioned bucket fallback
                out = self._s3.list_objects_v2(Bucket=self._cfg.bucket, Prefix=prefix)
                for o in out.get("Contents", []):
                    self._s3.delete_object(Bucket=self._cfg.bucket, Key=o["Key"])
                    count += 1
            mode = "lifecycle-tagged" if self._cfg.object_lock_mode == "compliance" else "deleted"
            return count, mode

        return await asyncio.to_thread(_delete)
