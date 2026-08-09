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
from urllib.parse import urlparse

from django.conf import settings

from apps.migration_cloud import defaults as mc_defaults

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
    existing = MigrationAsset.objects.filter(  # tenant-isolation-allow: scoped via bundle FK (bundle.school)
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
    bundle = MigrationBundle.objects.get(pk=bundle_id)  # tenant-isolation-allow: PK lookup by internal id from caller
    pending = MigrationAsset.objects.filter(  # tenant-isolation-allow: scoped via bundle FK (bundle.school)
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


def _asset_max_bytes() -> int:
    """Per-asset byte ceiling — a photo / scan / PDF, not a whole bundle."""
    try:
        return int(mc_defaults.get("migration_cloud.assets.max_asset_bytes"))
    except Exception:  # noqa: BLE001 — safe fallback
        return 64 * 1024 * 1024


def _asset_http_timeout() -> float:
    try:
        return float(mc_defaults.get("migration_cloud.assets.http_timeout_seconds"))
    except Exception:  # noqa: BLE001
        return 30.0


def _allow_local_file_source() -> bool:
    """Whether a ``file://`` / local-path asset source is permitted (default no)."""
    try:
        return bool(mc_defaults.get("migration_cloud.assets.allow_local_file_source"))
    except Exception:  # noqa: BLE001
        return False


def _fetch_uri(uri: str) -> tuple[bytes | None, str]:
    """Fetch bytes from a supported URI scheme, SSRF- and size-guarded.

    ``source_uri`` comes straight off a migrated SIS row (``photo_url``,
    ``report_card_url``, …) via ``detect_and_register_assets`` — it is
    UNTRUSTED. So:
      * http/https are SSRF-guarded (no loopback / RFC-1918 / metadata IP, every
        redirect re-validated) and streamed under a per-asset byte cap;
      * ``file://`` / bare local paths are REFUSED by default — a cloud tenant
        must never make the server read its own disk (``file:///etc/passwd``) —
        and only permitted, confined to MEDIA_ROOT, when a self-host opts in via
        ``migration_cloud.assets.allow_local_file_source``;
      * ``data:`` and ``s3://`` bodies are capped too.
    """
    parsed = urlparse(uri)
    scheme = (parsed.scheme or "").lower()
    max_bytes = _asset_max_bytes()

    if scheme in ("http", "https"):
        from .intake.net_guard import fetch_http_capped

        return fetch_http_capped(
            uri, max_bytes=max_bytes, timeout=_asset_http_timeout(),
        )

    if scheme in ("", "file"):
        return _read_local_asset(uri, parsed, max_bytes)

    if scheme == "data":
        # data:[<mime>][;base64],<payload>
        meta, _, payload = uri[len("data:"):].partition(",")
        mime = meta.split(";")[0] if meta else ""
        if "base64" in meta:
            import base64
            raw = base64.b64decode(payload)
        else:
            raw = payload.encode("utf-8")
        if len(raw) > max_bytes:
            raise ValueError(f"data: asset exceeds cap ({max_bytes:,} bytes)")
        return raw, mime

    if scheme == "s3":
        try:
            import boto3  # type: ignore[import-not-found]
        except ImportError:
            return None, ""
        bucket = parsed.netloc
        key = parsed.path.lstrip("/")
        s3 = boto3.client("s3")
        resp = s3.get_object(Bucket=bucket, Key=key)
        size = int(resp.get("ContentLength", 0) or 0)
        if size and size > max_bytes:
            raise ValueError(f"s3 asset is {size:,} bytes; exceeds cap {max_bytes:,}")
        return resp["Body"].read(), resp.get("ContentType", "")

    return None, ""


def _read_local_asset(uri: str, parsed, max_bytes: int) -> tuple[bytes | None, str]:
    """Read a ``file://`` / local-path asset — refused unless opted in + confined."""
    if not _allow_local_file_source():
        raise ValueError(
            "Refusing to read a local-file asset source (SSRF/LFI guard): a "
            f"migrated row supplied {uri!r}. Enable "
            "migration_cloud.assets.allow_local_file_source only on a self-host "
            "that confines assets to MEDIA_ROOT."
        )
    # Windows-tolerant file URI parse: ``file:///C:/path`` and ``file://C:\\path``.
    candidate = ""
    if uri.startswith("file://"):
        stripped = uri[len("file://"):]
        if stripped.startswith("/") and len(stripped) > 3 and stripped[2] == ":":
            candidate = stripped[1:]
        else:
            candidate = stripped
    path = Path(candidate or parsed.path or uri)
    try:
        configured_root = str(
            mc_defaults.get("migration_cloud.assets.local_source_root") or ""
        ).strip()
    except Exception:  # noqa: BLE001
        configured_root = ""
    root_dir = (
        Path(configured_root)
        if configured_root
        else Path(getattr(settings, "MEDIA_ROOT", "media"))
    )
    try:
        real = path.resolve()
        root = root_dir.resolve()
    except OSError as exc:
        raise ValueError(f"could not resolve local asset path: {exc}") from exc
    if not (real == root or real.is_relative_to(root)):
        raise ValueError(
            f"local asset path escapes the allowed asset root (path traversal "
            f"refused): {uri!r}"
        )
    if not real.exists() or not real.is_file():
        return None, ""
    size = real.stat().st_size
    if size > max_bytes:
        raise ValueError(f"local asset is {size:,} bytes; exceeds cap {max_bytes:,}")
    return real.read_bytes(), _guess_mime(real.name)


def _guess_mime(filename: str) -> str:
    import mimetypes

    mime, _ = mimetypes.guess_type(filename)
    return mime or ""
