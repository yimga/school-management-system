"""
Persist tenant brand assets during control-plane provisioning.
"""

from __future__ import annotations

from typing import BinaryIO

from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile

from apps.platform_runtime.storage import get_storage_url, tenant_media_path

MAX_LOGO_BYTES = 2 * 1024 * 1024
MAX_FAVICON_BYTES = 512 * 1024

ALLOWED_IMAGE_CONTENT_TYPES = frozenset(
    {
        "image/png",
        "image/jpeg",
        "image/jpg",
        "image/webp",
        "image/svg+xml",
        "image/x-icon",
        "image/vnd.microsoft.icon",
    }
)

_EXT_BY_CONTENT_TYPE = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/webp": ".webp",
    "image/svg+xml": ".svg",
    "image/x-icon": ".ico",
    "image/vnd.microsoft.icon": ".ico",
}

_LOGO_EXTENSIONS = (".png", ".jpg", ".jpeg", ".webp", ".svg")
_FAVICON_EXTENSIONS = (".png", ".ico", ".jpg", ".jpeg", ".webp", ".svg")


def _asset_extension(uploaded_file, *, allowed_ext: tuple[str, ...]) -> str:
    content_type = (getattr(uploaded_file, "content_type", None) or "").split(";")[0].strip().lower()
    if content_type in _EXT_BY_CONTENT_TYPE:
        ext = _EXT_BY_CONTENT_TYPE[content_type]
        if ext in allowed_ext or ext.lstrip(".") in {e.lstrip(".") for e in allowed_ext}:
            return ext
    name = (getattr(uploaded_file, "name", None) or "").lower()
    for ext in allowed_ext:
        if name.endswith(ext):
            return ext if ext != ".jpeg" else ".jpg"
    return allowed_ext[0] if allowed_ext else ".png"


def validate_brand_image_upload(
    uploaded_file,
    *,
    label: str,
    max_bytes: int,
    allowed_ext: tuple[str, ...],
    required: bool = True,
) -> None:
    if not uploaded_file:
        if required:
            raise ValidationError(f"{label} file is required")
        return
    size = int(getattr(uploaded_file, "size", 0) or 0)
    if size <= 0:
        raise ValidationError(f"{label} file is empty")
    if size > max_bytes:
        raise ValidationError(f"{label} must be {max_bytes // 1024} KB or smaller")
    content_type = (getattr(uploaded_file, "content_type", None) or "").split(";")[0].strip().lower()
    name = (getattr(uploaded_file, "name", "") or "").lower()
    ext_ok = any(name.endswith(ext) for ext in allowed_ext)
    if content_type and content_type not in ALLOWED_IMAGE_CONTENT_TYPES and not ext_ok:
        raise ValidationError(f"{label} must be PNG, ICO, JPEG, WebP, or SVG")
    if content_type == "image/svg+xml" or name.endswith(".svg"):
        from apps.siteconfig.svg_sanitize import validate_svg_safe

        validate_svg_safe(uploaded_file)


def validate_logo_upload(uploaded_file) -> None:
    validate_brand_image_upload(
        uploaded_file,
        label="logo",
        max_bytes=MAX_LOGO_BYTES,
        allowed_ext=_LOGO_EXTENSIONS,
        required=True,
    )


def validate_favicon_upload(uploaded_file) -> None:
    validate_brand_image_upload(
        uploaded_file,
        label="favicon",
        max_bytes=MAX_FAVICON_BYTES,
        allowed_ext=_FAVICON_EXTENSIONS,
        required=False,
    )


def _read_upload(uploaded_file: BinaryIO) -> bytes:
    if hasattr(uploaded_file, "seek"):
        uploaded_file.seek(0)
    data = uploaded_file.read()
    if hasattr(uploaded_file, "seek"):
        uploaded_file.seek(0)
    return data


def _persist_brand_file(*, school, uploaded_file, storage_basename: str) -> tuple[str, str]:
    from django.core.files.storage import default_storage

    if storage_basename == "logo":
        validate_logo_upload(uploaded_file)
        allowed_ext = _LOGO_EXTENSIONS
    else:
        validate_favicon_upload(uploaded_file)
        allowed_ext = _FAVICON_EXTENSIONS
    ext = _asset_extension(uploaded_file, allowed_ext=allowed_ext)
    storage_path = tenant_media_path(school.pk, f"brand/{storage_basename}{ext}")
    if default_storage.exists(storage_path):
        default_storage.delete(storage_path)
    default_storage.save(storage_path, ContentFile(_read_upload(uploaded_file)))
    return get_storage_url(storage_path), storage_path


def _touch_provisioning_flag(school, *, uploaded_key: str, storage_key: str, storage_path: str) -> None:
    settings = dict(getattr(school, "settings", None) or {})
    provisioning = dict(settings.get("provisioning") or {})
    provisioning[uploaded_key] = True
    provisioning[storage_key] = storage_path
    settings["provisioning"] = provisioning
    school.settings = settings
    school.save(update_fields=["settings"])


def persist_school_brand_logo(*, school, uploaded_file) -> str:
    """
    Store logo under tenants/{school_id}/brand/ and sync School + BrandProfile URLs.
    Returns the public storage URL.
    """
    from apps.brand_experience.models import BrandProfile

    logo_url, storage_path = _persist_brand_file(
        school=school, uploaded_file=uploaded_file, storage_basename="logo"
    )

    school.logo_url = logo_url
    school.save(update_fields=["logo_url"])

    profile, _created = BrandProfile.objects.get_or_create(
        school=school,
        defaults={
            "primary_color": getattr(school, "primary_color", None) or "#0d6efd",
            "accent_color": getattr(school, "accent_color", None) or "#198754",
        },
    )
    if profile.logo_url != logo_url:
        profile.logo_url = logo_url
        profile.save(update_fields=["logo_url", "updated_at"])

    _touch_provisioning_flag(
        school,
        uploaded_key="logo_uploaded",
        storage_key="logo_storage_path",
        storage_path=storage_path,
    )

    return logo_url


def persist_school_brand_favicon(*, school, uploaded_file) -> str:
    """Store favicon under tenants/{school_id}/brand/ and sync BrandProfile."""
    from apps.brand_experience.models import BrandProfile

    if not uploaded_file:
        return ""
    favicon_url, storage_path = _persist_brand_file(
        school=school, uploaded_file=uploaded_file, storage_basename="favicon"
    )

    profile, _created = BrandProfile.objects.get_or_create(
        school=school,
        defaults={
            "primary_color": getattr(school, "primary_color", None) or "#0d6efd",
            "accent_color": getattr(school, "accent_color", None) or "#198754",
            "logo_url": getattr(school, "logo_url", None) or "",
        },
    )
    if profile.favicon_url != favicon_url:
        profile.favicon_url = favicon_url
        profile.save(update_fields=["favicon_url", "updated_at"])

    _touch_provisioning_flag(
        school,
        uploaded_key="favicon_uploaded",
        storage_key="favicon_storage_path",
        storage_path=storage_path,
    )

    return favicon_url


# tenant-isolation-allow: school-brand-asset-owned-by-school-fk-only
# Day-1 Magic uses ``LogoUploadValidator`` to gate the operator-driven logo
# upload BEFORE the bytes ever land on disk. This is a stricter contract than
# ``validate_logo_upload`` above: PNG/JPEG/WebP only (no SVG — XSS risk),
# 1.5 MB hard cap, MIME determined by sniffing the magic bytes rather than
# trusting the upload's declared content_type or filename extension.


DAY1_LOGO_MAX_BYTES = 1_500_000
DAY1_LOGO_ALLOWED_MIME = frozenset({"image/png", "image/jpeg", "image/webp"})
DAY1_LOGO_FORBIDDEN_MIME = frozenset({"image/svg+xml", "image/svg"})


def _sniff_image_mime(image_bytes: bytes) -> str:
    """Return the most-specific image MIME we can confidently identify.

    Looks at the leading magic bytes; never trusts the caller's declared
    content-type. Returns ``""`` when the format is unknown.
    """
    if not image_bytes:
        return ""
    head = image_bytes[:16]
    # PNG: 89 50 4E 47 0D 0A 1A 0A
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    # JPEG: FF D8 FF
    if head.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    # WebP: "RIFF....WEBP"
    if head.startswith(b"RIFF") and len(image_bytes) >= 12 and image_bytes[8:12] == b"WEBP":
        return "image/webp"
    # GIF (we reject GIF too, but identifying it gives a useful error message)
    if head.startswith(b"GIF87a") or head.startswith(b"GIF89a"):
        return "image/gif"
    # SVG: ``<?xml`` or ``<svg`` near the start
    lowered = head.lower().lstrip()
    if lowered.startswith(b"<?xml") or lowered.startswith(b"<svg"):
        return "image/svg+xml"
    return ""


def LogoUploadValidator(image_bytes: bytes) -> tuple[bool, str]:  # noqa: N802
    """Day-1 Magic logo gatekeeper.

    Returns ``(True, "image/png")`` (or ``"image/jpeg"`` / ``"image/webp"``)
    when the bytes are an acceptable raster logo. Returns ``(False, reason)``
    otherwise. The MIME is determined by sniffing the file magic; the caller's
    declared content_type and filename extension are deliberately ignored so
    a maliciously-renamed SVG cannot slip past the XSS gate.
    """
    if image_bytes is None:
        return False, "empty upload"
    if not isinstance(image_bytes, (bytes, bytearray, memoryview)):
        return False, "upload must be bytes"
    image_bytes = bytes(image_bytes)
    size = len(image_bytes)
    if size == 0:
        return False, "empty upload"
    if size > DAY1_LOGO_MAX_BYTES:
        return False, f"logo exceeds {DAY1_LOGO_MAX_BYTES // 1024} KB cap"

    mime = _sniff_image_mime(image_bytes)
    if mime in DAY1_LOGO_FORBIDDEN_MIME:
        return False, "SVG logos are not accepted for Day-1 brand seeding (XSS risk)"
    if mime not in DAY1_LOGO_ALLOWED_MIME:
        return False, "logo must be PNG, JPEG, or WebP (sniffed by magic bytes)"

    return True, mime


def extract_brand_seed_from_logo(school) -> str | None:
    """Return a single ``#rrggbb`` hex string sampled from ``school.logo_url``.

    Wraps E1's ``services.theme_intelligence.extract_dominant_colors_from_image``
    with a lazy import + try/ImportError fallback so this helper is safe to
    call before Pillar 1 lands. Returns ``None`` when no logo is configured
    or extraction is unavailable / failed.
    """
    if school is None:
        return None
    logo_url = (getattr(school, "logo_url", None) or "").strip()
    if not logo_url:
        return None
    try:
        from services.theme_intelligence import (  # type: ignore[import-not-found]
            extract_dominant_colors_from_image,
        )
    except ImportError:
        return None
    try:
        result = extract_dominant_colors_from_image(logo_url)
    except Exception:
        return None
    if isinstance(result, str):
        return result
    if isinstance(result, (list, tuple)) and result:
        first = result[0]
        # The service returns list[ExtractedColor] (a dataclass with a .hex str);
        # tolerate a legacy list[str] too.
        hex_val = getattr(first, "hex", None)
        if isinstance(hex_val, str) and hex_val:
            return hex_val
        if isinstance(first, str):
            return first
    if isinstance(result, dict):
        for key in ("dominant", "seed_hex", "primary"):
            val = result.get(key)
            if isinstance(val, str):
                return val
    return None


def ensure_brand_profile_colors(*, school, primary_color: str, accent_color: str) -> None:
    from apps.brand_experience.models import BrandProfile

    profile, _created = BrandProfile.objects.get_or_create(
        school=school,
        defaults={
            "primary_color": primary_color,
            "accent_color": accent_color,
            "logo_url": getattr(school, "logo_url", None) or "",
        },
    )
    updates: list[str] = []
    if profile.primary_color != primary_color:
        profile.primary_color = primary_color
        updates.append("primary_color")
    if profile.accent_color != accent_color:
        profile.accent_color = accent_color
        updates.append("accent_color")
    if updates:
        updates.append("updated_at")
        profile.save(update_fields=updates)
