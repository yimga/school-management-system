"""Compile, sign, and persist daily tenant immutable snapshots."""

from __future__ import annotations

import gzip
import hashlib
import hmac
import json
import logging
import shutil
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from django.conf import settings

logger = logging.getLogger(__name__)


def _signing_key(school_id: str) -> bytes:
    material = (
        str(getattr(settings, "SECRET_KEY", "") or "")
        + ":tenant-snapshot:"
        + str(school_id)
    ).encode("utf-8")
    return hashlib.sha256(material).digest()


def sign_payload(payload_bytes: bytes, *, school_id: str) -> str:
    return hmac.new(_signing_key(school_id), payload_bytes, hashlib.sha256).hexdigest()


def verify_signature(payload_bytes: bytes, signature_hex: str, *, school_id: str) -> bool:
    expected = sign_payload(payload_bytes, school_id=school_id)
    return hmac.compare_digest(expected, str(signature_hex or ""))


def _snapshot_roots() -> tuple[Path, Path]:
    repo = Path(getattr(settings, "BASE_DIR", ".")).resolve()
    primary = repo / "var" / "tenant_snapshots" / "primary"
    secondary = repo / "var" / "tenant_snapshots" / "secondary"
    primary.mkdir(parents=True, exist_ok=True)
    secondary.mkdir(parents=True, exist_ok=True)
    return primary, secondary


def compile_snapshot_payload(school) -> dict[str, Any]:
    """Aggregate-only tenant state for DR (no raw student PII)."""
    from apps.schools.models import SchoolMembership
    from apps.people.models import StudentProfile, TeacherProfile
    from apps.finance.models import Invoice, Payment

    sid = str(school.pk)
    return {
        "schema_version": "1.0",
        "school_id": sid,
        "slug": getattr(school, "slug", ""),
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "counts": {
            "memberships": SchoolMembership.objects.filter(school=school).count(),
            "students": StudentProfile.objects.filter(school=school).count(),
            "teachers": TeacherProfile.objects.filter(school=school).count(),
            "invoices": Invoice.objects.filter(school=school).count(),
            "payments": Payment.objects.filter(school=school).count(),
        },
    }


def _maybe_upload_object_storage(*, local_path: Path, object_key: str) -> str | None:
    """Optional S3-compatible secondary when ``TENANT_SNAPSHOT_S3_BUCKET`` is set."""
    bucket = (getattr(settings, "TENANT_SNAPSHOT_S3_BUCKET", None) or "").strip()
    if not bucket:
        return None
    try:
        import boto3  # type: ignore[import-untyped]
    except ImportError:
        logger.warning("tenant_snapshot_s3_skipped boto3_unavailable bucket=%s", bucket)
        return None
    client = boto3.client(
        "s3",
        endpoint_url=getattr(settings, "TENANT_SNAPSHOT_S3_ENDPOINT", None) or None,
    )
    client.upload_file(str(local_path), bucket, object_key)
    uri = f"s3://{bucket}/{object_key}"
    logger.info("tenant_snapshot_s3_uploaded uri=%s bytes=%s", uri, local_path.stat().st_size)
    return uri


def capture_daily_snapshot(school, *, snapshot_date: date | None = None) -> dict[str, Any]:
    """Write gzip JSON to primary + secondary stores; persist metadata row."""
    from apps.lifecycle.models_dr_snapshot import TenantImmutableSnapshot

    day = snapshot_date or datetime.now(timezone.utc).date()
    payload = compile_snapshot_payload(school)
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    compressed = gzip.compress(raw)
    digest = hashlib.sha256(compressed).hexdigest()
    sig = sign_payload(compressed, school_id=str(school.pk))

    primary_root, secondary_root = _snapshot_roots()
    fname = f"{getattr(school, 'slug', school.pk)}_{day.isoformat()}.json.gz"
    primary_path = primary_root / fname
    secondary_path = secondary_root / fname
    primary_path.write_bytes(compressed)
    shutil.copy2(primary_path, secondary_path)
    s3_uri = _maybe_upload_object_storage(
        local_path=secondary_path,
        object_key=f"tenant_snapshots/{getattr(school, 'slug', school.pk)}/{day.isoformat()}.json.gz",
    )

    row, _created = TenantImmutableSnapshot.objects.update_or_create(
        school=school,
        snapshot_date=day,
        defaults={
            "primary_uri": primary_path.as_posix(),
            "secondary_uri": s3_uri or secondary_path.as_posix(),
            "payload_sha256": digest,
            "signature_hex": sig,
            "byte_size": len(compressed),
        },
    )
    return {
        "snapshot_id": str(row.pk),
        "school_id": str(school.pk),
        "snapshot_date": day.isoformat(),
        "byte_size": len(compressed),
        "payload_sha256": digest,
        "signature_hex": sig,
        "primary_uri": row.primary_uri,
        "secondary_uri": row.secondary_uri,
    }


def restore_from_snapshot(path: Path, *, school_id: str, expected_sig: str) -> dict[str, Any]:
    """Verify signature + decompress snapshot; returns parsed payload."""
    data = path.read_bytes()
    if not verify_signature(data, expected_sig, school_id=school_id):
        raise ValueError("snapshot_signature_mismatch")
    import gzip

    payload = json.loads(gzip.decompress(data).decode("utf-8"))
    if str(payload.get("school_id")) != str(school_id):
        raise ValueError("snapshot_school_mismatch")
    return payload
