"""Portable school BRANDING — carry a tenant's logo + colours + brand profile
between deployments (cloud → offline edge box) so a self-hosted school looks like
itself with no internet.

The tenant DATA bundle (:mod:`apps.lifecycle.tenant_portability`) and the identity
bundle deliberately carry ZERO branding/media — ``School`` is a public parent,
excluded from both. This is the third, dedicated artifact that closes that gap
(the ".rmcbrand" file), and it is what runbook step 4 (``media_branding``) hands to
the box.

Robustness — the logo must render OFFLINE:
  * It travels as a DB-resident base64 data URI in
    ``branding_metadata['logo_data_uri']`` — which :mod:`apps.siteconfig.branding`
    resolves FIRST, ahead of any URL — so it shows on the box with no media server,
    no DNS, and no file on disk. This is the primary mechanism.
  * The raw bytes are ALSO written into the box ``MEDIA_ROOT`` and ``logo_url`` is
    set to a box-relative ``/media/…`` path — a belt-and-suspenders fallback that,
    unlike the old ``https://{slug}.school.lan/…`` URL, actually resolves on a box
    with no LAN DNS.

Envelope (encrypt-then-MAC, fail-closed) is reused verbatim from
:mod:`apps.lifecycle.tenant_dr_snapshot` — no new crypto — mirroring
``tenant_portability``'s container shape.
"""
from __future__ import annotations

import base64
import gzip
import json
import logging
import os

from django.core.files.storage import default_storage
from django.core.serializers.json import DjangoJSONEncoder
from django.utils import timezone

from apps.lifecycle.tenant_dr_snapshot import (
    decrypt_blob,
    encrypt_blob,
    sign_payload,
    verify_signature,
)
from apps.platform_runtime.storage import (
    get_storage_url,
    save_to_storage,
    tenant_media_path,
)

logger = logging.getLogger(__name__)

BRANDING_BUNDLE_FORMAT = "rmc-brand-bundle/1"

# School scalar branding fields that travel (URL-ish + colours). branding_metadata
# is carried separately (it holds the offline-critical logo_data_uri).
_SCHOOL_BRAND_FIELDS = ("logo_url", "wallpaper_url", "primary_color", "accent_color")

# Every persisted BrandProfile field except pk / school / auto timestamps.
_BRAND_PROFILE_FIELDS = (
    "logo_url", "logo_dark_url", "favicon_url", "tagline", "primary_color",
    "secondary_color", "accent_color", "font_family", "login_background_url",
    "portal_visual", "email_template", "pdf_template", "certificate_template",
    "tokens", "templates", "assets", "custom_css",
)

_EXT_BY_CT = {
    "image/png": ".png", "image/jpeg": ".jpg", "image/svg+xml": ".svg",
    "image/webp": ".webp", "image/gif": ".gif",
}
_CT_BY_EXT = {
    ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
    ".svg": "image/svg+xml", ".webp": "image/webp", ".gif": "image/gif",
}


def _ext_for_ct(content_type: str) -> str:
    return _EXT_BY_CT.get((content_type or "").split(";")[0].strip().lower(), ".png")


def _ct_for_name(name: str) -> str:
    return _CT_BY_EXT.get(os.path.splitext(name or "")[1].lower(), "application/octet-stream")


def _to_data_uri(raw: bytes, content_type: str) -> str:
    ct = (content_type or "image/png").split(";")[0].strip() or "image/png"
    return f"data:{ct};base64,{base64.b64encode(raw).decode('ascii')}"


def _decode_data_uri(uri: str) -> tuple[bytes | None, str]:
    try:
        head, b64 = uri.split(",", 1)
        ct = "image/png"
        if head.startswith("data:"):
            ct = head[len("data:"):].split(";", 1)[0] or "image/png"
        return base64.b64decode(b64), ct
    except Exception:  # noqa: BLE001 — a malformed data URI is simply "no bytes"
        return None, ""


def _media_relpath(url: str) -> str | None:
    """Turn a ``/media/…`` (or ``https://host/media/…``) URL into a storage key."""
    from django.conf import settings

    media_url = (getattr(settings, "MEDIA_URL", "/media/") or "/media/")
    marker = media_url if media_url.startswith("/") else "/" + media_url.split("://", 1)[-1].split("/", 1)[-1]
    marker = "/media/" if not marker else marker
    url = (url or "").strip()
    if not url:
        return None
    idx = url.find(marker)
    if idx == -1:
        # A bare relative storage key (already what default_storage expects).
        if url.startswith("tenants/"):
            return url
        return None
    return url[idx + len(marker):].lstrip("/") or None


def _read_storage(path: str) -> bytes | None:
    try:
        if not default_storage.exists(path):
            return None
        with default_storage.open(path, "rb") as fh:
            return fh.read()
    except Exception:  # noqa: BLE001 — best-effort; absence of bytes is not fatal
        logger.debug("branding_portability: could not read %s", path, exc_info=True)
        return None


def _read_logo_bytes(school, metadata: dict) -> tuple[bytes | None, str, str]:
    """Resolve the school's logo bytes from (in priority) an inline data URI, the
    stored path recorded at upload, or a ``/media/…`` logo_url. Returns
    ``(bytes|None, content_type, filename)``."""
    data_uri = str(metadata.get("logo_data_uri") or "")
    if data_uri.startswith("data:"):
        raw, ct = _decode_data_uri(data_uri)
        if raw:
            return raw, ct, f"logo{_ext_for_ct(ct)}"

    stored = str(metadata.get("logo_storage_path") or "")
    if stored:
        raw = _read_storage(stored)
        if raw:
            return raw, _ct_for_name(stored), os.path.basename(stored) or "logo"

    rel = _media_relpath(getattr(school, "logo_url", "") or "")
    if rel:
        raw = _read_storage(rel)
        if raw:
            return raw, _ct_for_name(rel), os.path.basename(rel) or "logo"

    return None, "", ""


def _export_brand_profile(school) -> dict | None:
    try:
        from apps.brand_experience.models import BrandProfile
    except Exception:  # noqa: BLE001
        return None
    profile = BrandProfile.objects.filter(school=school).first()
    if profile is None:
        return None
    return {f: getattr(profile, f, None) for f in _BRAND_PROFILE_FIELDS}


def export_school_branding(school) -> bytes:
    """Serialize a school's branding (logo bytes + colours + brand profile) into an
    encrypted + signed ``.rmcbrand`` container. Returns the container JSON bytes."""
    metadata = dict(getattr(school, "branding_metadata", None) or {})

    logo_bytes, logo_ct, logo_name = _read_logo_bytes(school, metadata)
    # Guarantee the logo travels DB-resident so it renders on the box with no media
    # server / no file. If it was only a file (not already a data URI), inline it.
    if logo_bytes and not str(metadata.get("logo_data_uri") or "").startswith("data:"):
        metadata["logo_data_uri"] = _to_data_uri(logo_bytes, logo_ct)

    assets: dict = {}
    if logo_bytes:
        assets["logo"] = {
            "filename": logo_name or f"logo{_ext_for_ct(logo_ct)}",
            "content_type": logo_ct or "image/png",
            "b64": base64.b64encode(logo_bytes).decode("ascii"),
        }

    payload = {
        "format": BRANDING_BUNDLE_FORMAT,
        "school_id": str(school.id),
        "tenant_slug": getattr(school, "slug", "") or "",
        "created_at_iso": timezone.now().isoformat(),
        "school_branding": {f: getattr(school, f, None) for f in _SCHOOL_BRAND_FIELDS},
        "branding_metadata": metadata,
        "brand_profile": _export_brand_profile(school),
        "assets": assets,
        "has_offline_logo": bool(metadata.get("logo_data_uri")),
    }
    raw = json.dumps(payload, cls=DjangoJSONEncoder).encode("utf-8")
    compressed = gzip.compress(raw)
    blob = encrypt_blob(compressed, school_id=str(school.id))
    sig = sign_payload(blob, school_id=str(school.id))
    container = {
        "format": BRANDING_BUNDLE_FORMAT,
        "school_id": str(school.id),
        "sig": sig,
        "blob_b64": base64.b64encode(blob).decode("ascii"),
    }
    return json.dumps(container).encode("utf-8")


def _import_brand_profile(school, fields: dict | None) -> bool:
    if not fields:
        return False
    try:
        from apps.brand_experience.models import BrandProfile
    except Exception:  # noqa: BLE001
        return False
    clean = {k: v for k, v in fields.items() if k in _BRAND_PROFILE_FIELDS and v is not None}
    if not clean:
        return False
    BrandProfile.objects.update_or_create(school=school, defaults=clean)
    return True


def import_school_branding(container_bytes: bytes, *, school, write_media: bool = True) -> dict:
    """Verify, decrypt, and apply a ``.rmcbrand`` bundle onto ``school``.

    Fail-closed: the HMAC signature (bound to the source school id) is verified
    BEFORE any decrypt. Applies the branding to the passed (box-side) school —
    branding is identity-agnostic content, so the box school need not share the
    source pk. The logo always ends up renderable offline via
    ``branding_metadata['logo_data_uri']``; the raw bytes are additionally written
    to the box MEDIA_ROOT with ``logo_url`` set to a box-relative ``/media/…`` path.
    """
    container = json.loads(container_bytes)
    if container.get("format") != BRANDING_BUNDLE_FORMAT:
        raise ValueError(f"not a branding bundle (format={container.get('format')!r})")
    source_school_id = str(container["school_id"])
    blob = base64.b64decode(container["blob_b64"])
    if not verify_signature(blob, container["sig"], school_id=source_school_id):
        raise ValueError("branding_bundle_signature_mismatch")  # fail closed

    payload = json.loads(gzip.decompress(decrypt_blob(blob, school_id=source_school_id)))

    metadata = dict(payload.get("branding_metadata") or {})
    school_branding = dict(payload.get("school_branding") or {})
    assets = dict(payload.get("assets") or {})

    media_written: list[str] = []
    logo_url_final = school_branding.get("logo_url") or ""

    if write_media and assets.get("logo"):
        try:
            logo = assets["logo"]
            raw = base64.b64decode(logo["b64"])
            ext = os.path.splitext(logo.get("filename") or "")[1].lower() or _ext_for_ct(
                logo.get("content_type")
            )
            rel = tenant_media_path(school.pk, f"brand/logo{ext}")
            # save_to_storage returns the ACTUAL stored key (storage may append a
            # suffix to avoid clobbering an existing file) — use that, not the input.
            stored_rel = save_to_storage(rel, raw, logo.get("content_type"))
            logo_url_final = get_storage_url(stored_rel)  # box-resolvable /media/… path
            metadata["logo_storage_path"] = stored_rel
            media_written.append(stored_rel)
        except Exception:  # noqa: BLE001 — the DB-resident data URI still renders offline
            logger.warning("branding_portability: media write failed; relying on data URI", exc_info=True)

    # Merge branding_metadata (carrying logo_data_uri = the offline-safe logo).
    merged_md = dict(getattr(school, "branding_metadata", None) or {})
    merged_md.update(metadata)
    school.branding_metadata = merged_md

    updated_fields = ["branding_metadata"]
    for field, value in school_branding.items():
        if field == "logo_url":
            school.logo_url = logo_url_final or (value or "")
            updated_fields.append("logo_url")
        elif hasattr(school, field) and value is not None:
            setattr(school, field, value)
            updated_fields.append(field)

    school.save(update_fields=sorted(set(updated_fields)))
    profile_restored = _import_brand_profile(school, payload.get("brand_profile"))

    return {
        "ok": True,
        "source_school_id": source_school_id,
        "applied_to": str(school.id),
        "logo_offline_ok": bool(merged_md.get("logo_data_uri")),
        "media_written": media_written,
        "brand_profile_restored": profile_restored,
        "fields": sorted(set(updated_fields)),
    }
