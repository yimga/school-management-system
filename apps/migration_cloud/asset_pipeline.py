"""Binary asset pipeline — student photos, immunization scans, report-card PDFs.

Schools migrating from PowerSchool / Blackbaud / a custom SIS carry
non-tabular binary content alongside the rows: student photos,
immunization scans, ID-card images, PDF report cards. Until this module
existed, the orchestrator silently dropped these (only the PDF intake
adapter ever read a binary).

Public surface:
    * :func:`register_asset` — landers / mappers call this when they spot
      an asset URL/path on an incoming row.
    * :func:`fetch_pending_assets` — Celery task wrapper that streams each
      pending row's bytes to MEDIA_ROOT and flips status STORED / FAILED.
    * :func:`asset_storage_path` — deterministic per-tenant target path.

Storage layout::

    MEDIA_ROOT/migration_cloud/assets/<tenant_pk>/<entity_kind>/<legacy_id>.<ext>

This keeps the assets co-located with the row they belong to, idempotent
(re-fetching the same source replaces in-place), and trivially copyable
to S3 or any other backend behind ``django.core.files.storage``.
"""

from __future__ import annotations

import hashlib
import logging
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from django.conf import settings

from .models import AssetStatus, MigrationAsset, MigrationBundle

logger = logging.getLogger(__name__)


_SAFE_NAME_RE = re.compile(r"[^A-Za-z0-9_.-]+")
_EXT_FOR_MIME = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
    "application/pdf": ".pdf",
}


def asset_storage_path(*, bundle: MigrationBundle, asset: MigrationAsset) -> Path:
    """Deterministic absolute path under MEDIA_ROOT for a stored asset."""
    media_root = Path(getattr(settings, "MEDIA_ROOT", "media"))
    tenant_pk = getattr(bundle.school, "pk", "shared") if bundle.school_id else "shared"
    safe_legacy = _SAFE_NAME_RE.sub("_", asset.legacy_id or "unknown")
    ext = _EXT_FOR_MIME.get(asset.mime_type, "")
    if not ext:
        source = (asset.source_uri or "").lower()
        for candidate in (".pdf", ".png", ".jpg", ".jpeg", ".webp", ".gif"):
            if source.endswith(candidate):
                ext = candidate if candidate != ".jpeg" else ".jpg"
                break
    if not ext:
        ext = ".bin"
    return (
        media_root
        / "migration_cloud"
        / "assets"
        / str(tenant_pk)
        / asset.entity_kind
        / f"{safe_legacy}.{asset.asset_kind}{ext}"
    )


def register_asset(
    *,
    bundle: MigrationBundle,
    entity_kind: str,
    legacy_id: str,
    asset_kind: str,
    source_uri: str,
) -> MigrationAsset | None:
    """Register a pending asset for a row. Idempotent by (bundle, entity, legacy, kind, uri)."""
    if not source_uri or not legacy_id:
        return None
    existing = MigrationAsset.objects.filter(
        bundle=bundle,
        entity_kind=entity_kind,
        legacy_id=legacy_id,
        asset_kind=asset_kind,
        source_uri=source_uri,
    ).first()
    if existing is not None:
        return existing
    return MigrationAsset.objects.create(
        bundle=bundle,
        school=bundle.school,
        entity_kind=entity_kind,
        legacy_id=legacy_id,
        asset_kind=asset_kind,
        source_uri=source_uri,
    )


def fetch_pending_assets(*, bundle_id: int, max_batch: int = 100) -> dict[str, int]:
    """Fetch and store all PENDING assets for a bundle.

    Streams each asset's bytes, computes SHA256 on the fly, and writes to
    MEDIA_ROOT. Returns a summary of counts (stored / failed / skipped).
    """
    bundle = MigrationBundle.objects.get(pk=bundle_id)
    pending = MigrationAsset.objects.filter(
        bundle=bundle, status=AssetStatus.PENDING
    )[:max_batch]
    counts = {"stored": 0, "failed": 0, "skipped": 0}
    for asset in pending:
        asset.status = AssetStatus.FETCHING
        asset.save(update_fields=["status", "updated_at"])
        try:
            content, mime = _fetch_uri(asset.source_uri)
        except Exception as exc:  # noqa: BLE001
            logger.warning("asset_pipeline: fetch failed for asset=%s: %s", asset.pk, exc)
            asset.status = AssetStatus.FAILED
            asset.error = f"{type(exc).__name__}: {exc}"[:500]
            asset.save(update_fields=["status", "error", "updated_at"])
            counts["failed"] += 1
            continue
        if content is None:
            asset.status = AssetStatus.FAILED
            asset.error = "fetcher returned no content"
            asset.save(update_fields=["status", "error", "updated_at"])
            counts["failed"] += 1
            continue

        asset.mime_type = mime or asset.mime_type
        target = asset_storage_path(bundle=bundle, asset=asset)
        target.parent.mkdir(parents=True, exist_ok=True)
        digest = hashlib.sha256(content).hexdigest()
        target.write_bytes(content)
        asset.stored_path = str(target.relative_to(Path(getattr(settings, "MEDIA_ROOT", "media"))))
        asset.sha256 = digest
        asset.byte_size = len(content)
        asset.status = AssetStatus.STORED
        asset.error = ""
        asset.save(update_fields=[
            "mime_type", "stored_path", "sha256", "byte_size", "status", "error", "updated_at",
        ])
        counts["stored"] += 1
    return counts


def _fetch_uri(uri: str) -> tuple[bytes | None, str]:
    """Fetch bytes from any supported URI scheme. Returns (content, mime_type)."""
    parsed = urlparse(uri)
    scheme = (parsed.scheme or "").lower()

    if scheme in ("", "file"):
        # Windows-tolerant file URI parse: ``file:///C:/path`` and
        # ``file://C:\\path`` both have to resolve cleanly.
        candidate = ""
        if uri.startswith("file://"):
            stripped = uri[len("file://"):]
            if stripped.startswith("/") and len(stripped) > 3 and stripped[2] == ":":
                candidate = stripped[1:]
            else:
                candidate = stripped
        path = Path(candidate or parsed.path or uri)
        if not path.exists() or not path.is_file():
            return None, ""
        return path.read_bytes(), _guess_mime(path.name)

    if scheme in ("http", "https"):
        try:
            import urllib.request

            req = urllib.request.Request(uri, headers={"User-Agent": "RunMyCampus-MigrationCloud/1.0"})
            with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310 — operator-controlled URI
                mime = resp.headers.get("Content-Type", "").split(";")[0].strip()
                return resp.read(), mime
        except Exception:  # noqa: BLE001
            raise

    if scheme == "data":
        # data:[<mime>][;base64],<payload>
        meta, _, payload = uri[len("data:"):].partition(",")
        mime = meta.split(";")[0] if meta else ""
        if "base64" in meta:
            import base64
            return base64.b64decode(payload), mime
        return payload.encode("utf-8"), mime

    if scheme == "s3":
        try:
            import boto3  # type: ignore[import-not-found]
        except ImportError:
            return None, ""
        bucket = parsed.netloc
        key = parsed.path.lstrip("/")
        s3 = boto3.client("s3")
        resp = s3.get_object(Bucket=bucket, Key=key)
        return resp["Body"].read(), resp.get("ContentType", "")

    return None, ""


def _guess_mime(filename: str) -> str:
    import mimetypes

    mime, _ = mimetypes.guess_type(filename)
    return mime or ""
