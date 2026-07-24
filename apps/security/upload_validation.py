"""Shared upload-validation primitive.

One place every file-upload intake can route through so validation is
consistent and never accidentally skipped: a size cap, a magic-byte sniff (the
declared ``content_type`` / filename are client-supplied and are deliberately
ignored), a sniffed-MIME allowlist, and a pluggable malware-scan hook.

This generalises the magic-byte contract the brand-asset path
(:mod:`apps.schools.school_brand_assets`) already enforced for tenant logos —
so other intake points share ONE sniffer + one gate rather than each
reinventing (or silently skipping) it. See ``docs`` note in
``scripts/scan_upload_validation_coverage.py`` for the coverage ratchet.

Honesty note on malware scanning: the hook is real and wired, but there is no
bundled scanner. When ``settings.UPLOAD_MALWARE_SCANNER`` is unset,
:func:`scan_for_malware` returns ``(True, "av-not-configured")`` and logs a
one-time warning — it reports "not scanned", never "clean". A real
ClamAV / scanning-service backend is provisioned by operations and pointed at
via that setting; that remains external work.
"""

from __future__ import annotations

import logging
from importlib import import_module
from typing import Callable, Iterable, Optional, Tuple

from django.conf import settings
from django.core.exceptions import ValidationError

logger = logging.getLogger(__name__)


# Canonical sniffed-MIME allowlists. ``sniff_file_mime`` returns these strings.
SAFE_IMAGE_MIMES = frozenset({"image/png", "image/jpeg", "image/webp"})
RASTER_IMAGE_MIMES = frozenset(
    {"image/png", "image/jpeg", "image/webp", "image/gif", "image/bmp", "image/tiff"}
)
DOCUMENT_MIMES = frozenset({"application/pdf", "application/zip"})
# A photo/scan/PDF of a receipt or supporting document.
RECEIPT_MIMES = frozenset({"image/png", "image/jpeg", "application/pdf"})

# Read enough of the head to cover a PDF header that legally sits after leading
# bytes (spec allows up to ~1 KB); every other magic signature is in the first
# few bytes, so this is comfortably sufficient and still cheap.
_HEAD_BYTES = 1024
_AV_UNCONFIGURED_WARNED = False


class UploadValidationError(ValidationError):
    """Raised when an uploaded file fails a safety check.

    Subclasses ``django.core.exceptions.ValidationError`` so form / DRF layers
    already catching that keep working; call sites that just want a message use
    ``str(err)``.
    """


def sniff_file_mime(head: bytes) -> str:
    """Best-effort magic-byte sniff over the leading bytes of a file.

    Returns a canonical MIME string, or ``""`` when the format is unknown.
    Never trusts a declared content-type. Covers the raster images the shared
    image sniffer knows (png/jpeg/webp/gif/svg) plus BMP, TIFF, PDF, and the ZIP
    container family (xlsx/docx/…). The PDF header may legally sit after up to
    ~1 KB of leading bytes, so it is searched, not required at offset 0 (avoids
    over-rejecting valid-but-non-conformant PDFs). Text/CSV has no magic
    signature and is intentionally NOT sniffed — a caller that accepts CSV
    validates structure at parse time and marks the intake accordingly.
    """
    from apps.schools.school_brand_assets import sniff_image_mime

    image_mime = sniff_image_mime(head)
    if image_mime:
        return image_mime
    if not head:
        return ""
    if head[:2] == b"BM":
        return "image/bmp"
    if head[:4] in (b"II*\x00", b"MM\x00*"):
        return "image/tiff"
    if head[:4] in (b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08"):
        return "application/zip"
    if b"%PDF-" in head[:1024]:
        return "application/pdf"
    return ""


def _read_head(file_obj, n: int) -> bytes:
    try:
        file_obj.seek(0)
        head = file_obj.read(n)
        file_obj.seek(0)
    except (AttributeError, ValueError, OSError):
        return b""
    return head or b""


def _read_all(file_obj) -> bytes:
    try:
        file_obj.seek(0)
        data = file_obj.read()
        file_obj.seek(0)
    except (AttributeError, ValueError, OSError):
        return b""
    return data or b""


def _resolve_scanner() -> Optional[Callable[[bytes], Tuple[bool, str]]]:
    """Return the configured malware scanner callable, or ``None`` when unset.

    ``settings.UPLOAD_MALWARE_SCANNER`` may be a callable or a dotted
    ``"pkg.module.func"`` path. A misconfigured value fails closed for the
    scan step only (logged) — it never crashes the upload path.
    """
    target = getattr(settings, "UPLOAD_MALWARE_SCANNER", None)
    if target is None:
        return None
    if callable(target):
        return target
    if isinstance(target, str) and "." in target:
        module_path, _, attr = target.rpartition(".")
        try:
            return getattr(import_module(module_path), attr)
        except (ImportError, AttributeError):
            logger.error("UPLOAD_MALWARE_SCANNER=%r could not be imported", target)
            return None
    logger.error("UPLOAD_MALWARE_SCANNER=%r is not callable or a dotted path", target)
    return None


def scan_for_malware(data: bytes) -> Tuple[bool, str]:
    """Run the configured malware scan over ``data``.

    Returns ``(ok, detail)``. When no scanner is configured, returns
    ``(True, "av-not-configured")`` and logs a one-time warning — honest
    "not scanned", never a false "clean". A configured scanner that raises is
    treated as ``(False, ...)`` (fail-closed) so a broken scanner blocks rather
    than silently admits.
    """
    global _AV_UNCONFIGURED_WARNED
    scanner = _resolve_scanner()
    if scanner is None:
        if not _AV_UNCONFIGURED_WARNED:
            logger.warning(
                "No UPLOAD_MALWARE_SCANNER configured; uploads are size/type-gated "
                "but NOT malware-scanned. Point the setting at a scanning service."
            )
            _AV_UNCONFIGURED_WARNED = True
        return True, "av-not-configured"
    try:
        result = scanner(data)
    except Exception as exc:  # fail-closed: a broken scanner must not admit files
        logger.error("UPLOAD_MALWARE_SCANNER raised: %s", exc)
        return False, "scanner-error"
    if isinstance(result, tuple) and len(result) == 2:
        return bool(result[0]), str(result[1])
    return bool(result), ""


def validate_uploaded_file(
    file_obj,
    *,
    allowed_mimes: Iterable[str],
    max_bytes: int,
    av_scan: bool = True,
) -> str:
    """Validate an uploaded file end-to-end. Return the sniffed MIME on success.

    Raises :class:`UploadValidationError` on any failure:

    * empty file, or size greater than ``max_bytes`` (size is read from the
      upload's declared ``.size`` before any bytes are read into memory);
    * the sniffed magic-byte MIME is not in ``allowed_mimes`` (the declared
      content-type and filename are ignored — a renamed / spoofed file is
      caught here);
    * ``av_scan`` and a configured scanner reports the bytes unsafe.

    The file's read cursor is restored to 0 on every path, so the caller can
    save ``file_obj`` unchanged afterwards.
    """
    allowed = frozenset(allowed_mimes)
    size = int(getattr(file_obj, "size", 0) or 0)
    if size <= 0:
        raise UploadValidationError("The uploaded file is empty.")
    if size > max_bytes:
        raise UploadValidationError(
            f"The file is too large (limit {max_bytes // 1024} KB)."
        )

    mime = sniff_file_mime(_read_head(file_obj, _HEAD_BYTES))
    if mime not in allowed:
        raise UploadValidationError(
            "Unsupported or unrecognised file type (checked by content, not name)."
        )

    if av_scan and _resolve_scanner() is not None:
        ok, detail = scan_for_malware(_read_all(file_obj))
        if not ok:
            raise UploadValidationError(f"The file failed a security scan: {detail}")

    return mime
