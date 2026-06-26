"""Tenant-scoped media uploads for the login immersive canvas gallery."""

from __future__ import annotations

import hashlib
import logging
import uuid
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

_GALLERY_EXT_BY_MIME: dict[str, str] = {
    "image/png": "png",
    "image/jpeg": "jpg",
    "image/webp": "webp",
}


@dataclass(frozen=True)
class GalleryUploadResult:
    ok: bool
    public_url: str = ""
    storage_path: str = ""
    error_code: str = ""
    error_message: str = ""


def _school_log_label(school: Any) -> str:
    slug = str(getattr(school, "slug", "") or "")
    if not slug:
        return "unknown"
    return hashlib.sha256(slug.encode("utf-8")).hexdigest()[:8]


def accept_login_canvas_gallery_image(
    school: Any,
    image_bytes: bytes,
    *,
    original_filename: str = "",
) -> GalleryUploadResult:
    """Validate and persist a gallery image under the tenant media prefix."""
    if school is None:
        return GalleryUploadResult(
            ok=False,
            error_code="missing_tenant",
            error_message="school is required",
        )

    try:
        from apps.schools.school_brand_assets import LogoUploadValidator
    except Exception:
        logger.error(
            "login_canvas: gallery validator import failed tenant=%s",
            _school_log_label(school),
        )
        return GalleryUploadResult(
            ok=False,
            error_code="validator_unavailable",
            error_message="image validator is unavailable",
        )

    ok, payload = LogoUploadValidator(image_bytes)
    if not ok:
        return GalleryUploadResult(
            ok=False,
            error_code="invalid_image",
            error_message=str(payload or "invalid image"),
        )

    sniffed_mime = str(payload)
    ext = _GALLERY_EXT_BY_MIME.get(sniffed_mime, "png")

    try:
        storage_path, public_url = _persist_gallery_bytes(
            school=school,
            image_bytes=bytes(image_bytes),
            ext=ext,
        )
    except Exception:
        logger.warning(
            "login_canvas: gallery persist failed tenant=%s",
            _school_log_label(school),
            exc_info=True,
        )
        return GalleryUploadResult(
            ok=False,
            error_code="storage_failed",
            error_message="failed to persist image to storage",
        )

    _ = original_filename  # audit-only; never trusted for MIME or path
    logger.info(
        "login_canvas: gallery image stored tenant=%s path=%s",
        _school_log_label(school),
        storage_path.rsplit("/", 1)[-1],
    )
    return GalleryUploadResult(
        ok=True,
        public_url=public_url,
        storage_path=storage_path,
    )


def _persist_gallery_bytes(
    *,
    school: Any,
    image_bytes: bytes,
    ext: str,
) -> tuple[str, str]:
    from django.core.files.base import ContentFile
    from django.core.files.storage import default_storage

    from apps.platform_runtime.storage import get_storage_url, tenant_media_path

    safe_ext = (ext or "png").lstrip(".").lower()
    if safe_ext not in {"png", "jpg", "webp"}:
        safe_ext = "png"
    file_id = uuid.uuid4().hex
    storage_path = tenant_media_path(
        getattr(school, "pk", None),
        f"login_canvas/gallery/{file_id}.{safe_ext}",
    )
    # tenant-isolation-allow: login-canvas-gallery-upload-keyed-on-school-pk-only
    default_storage.save(storage_path, ContentFile(image_bytes))
    return storage_path, get_storage_url(storage_path)
