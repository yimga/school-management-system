"""Object-storage cleanup for tenant offboarding (S3 + local fallback)."""

from __future__ import annotations

import logging
import os
from typing import Any

from django.conf import settings

logger = logging.getLogger(__name__)


def _bucket_name() -> str | None:
    return (
        os.environ.get("AWS_STORAGE_BUCKET_NAME", "").strip()
        or getattr(settings, "AWS_STORAGE_BUCKET_NAME", None)
        or ""
    ).strip() or None


def s3_configured() -> bool:
    bucket = _bucket_name()
    if not bucket:
        return False
    try:
        import boto3  # noqa: F401
    except ImportError:
        return False
    return True


def list_tenant_object_keys(
    school_slug: str,
    school_id: str,
    *,
    max_keys: int = 5000,
) -> list[str]:
    """List object keys under tenant prefixes (S3 only)."""
    if not s3_configured():
        return []
    from apps.schools.tenant_offboarding_policy import tenant_media_prefixes

    import boto3

    bucket = _bucket_name()
    client = boto3.client("s3")
    prefixes = tenant_media_prefixes(school_slug, school_id)
    keys: list[str] = []
    for prefix in prefixes:
        token = None
        while len(keys) < max_keys:
            kwargs: dict[str, Any] = {"Bucket": bucket, "Prefix": prefix, "MaxKeys": 1000}
            if token:
                kwargs["ContinuationToken"] = token
            resp = client.list_objects_v2(**kwargs)
            for item in resp.get("Contents") or []:
                key = item.get("Key")
                if key:
                    keys.append(str(key))
                    if len(keys) >= max_keys:
                        break
            if not resp.get("IsTruncated"):
                break
            token = resp.get("NextContinuationToken")
    return keys


def delete_tenant_s3_objects(
    school_slug: str,
    school_id: str,
    *,
    dry_run: bool = True,
    retain_archives: bool = True,
) -> dict[str, Any]:
    """
    Delete S3 objects under tenant prefixes. Archives retained by default.
    """
    keys = list_tenant_object_keys(school_slug, school_id)
    if retain_archives:
        keys = [k for k in keys if not k.startswith(f"tenant_archives/{school_slug}/")]
    if not keys:
        return {
            "backend": "s3" if s3_configured() else "none",
            "dry_run": dry_run,
            "deleted_count": 0,
            "keys": [],
        }
    if dry_run or not s3_configured():
        return {
            "backend": "s3" if s3_configured() else "none",
            "dry_run": True,
            "deleted_count": len(keys),
            "keys": keys[:100],
        }

    import boto3

    bucket = _bucket_name()
    client = boto3.client("s3")
    deleted = 0
    errors: list[str] = []
    for i in range(0, len(keys), 1000):
        batch = keys[i : i + 1000]
        try:
            resp = client.delete_objects(
                Bucket=bucket,
                Delete={"Objects": [{"Key": k} for k in batch], "Quiet": True},
            )
            deleted += len(resp.get("Deleted") or [])
            for err in resp.get("Errors") or []:
                errors.append(f"{err.get('Key','?')}:{err.get('Code','')}")
        except Exception as exc:
            errors.append(type(exc).__name__)
            logger.warning(
                "tenant_offboarding s3 batch delete failed slug=%s err=%s",
                school_slug,
                type(exc).__name__,
            )
    return {
        "backend": "s3",
        "dry_run": False,
        "deleted_count": deleted,
        "errors": errors[:20],
        "keys_sample": keys[:20],
    }


def lifecycle_policy_document(*, bucket: str | None = None) -> dict[str, Any]:
    """
    Recommended bucket lifecycle rules (operator applies in AWS console/Terraform).
    Does not call AWS APIs — documents the contract.
    """
    bucket = bucket or _bucket_name() or "<your-media-bucket>"
    return {
        "Rules": [
            {
                "ID": "rmc-tenant-archive-transition",
                "Status": "Enabled",
                "Filter": {"Prefix": "tenant_archives/"},
                "Transitions": [
                    {"Days": 90, "StorageClass": "STANDARD_IA"},
                    {"Days": 365, "StorageClass": "GLACIER"},
                ],
            },
            {
                "ID": "rmc-tenant-upload-expire",
                "Status": "Enabled",
                "Filter": {"Prefix": "tenants/"},
                "Expiration": {"Days": 0},
                "NoncurrentVersionExpiration": {"NoncurrentDays": 30},
                "AbortIncompleteMultipartUpload": {"DaysAfterInitiation": 7},
            },
        ],
        "_comment": f"Attach to bucket {bucket}; Expiration Days=0 means use tag rmco-offboarding-purge=pending",
    }
