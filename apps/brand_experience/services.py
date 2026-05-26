"""Brand experience service entry points.

Thin domain helpers that the Unified Wizard Framework (and any other caller)
uses to propagate brand changes into first-class models on top of the
``SiteSettings.cockpit_payload`` 7-layer cascade fallback.

Idempotent, no-op-friendly: every helper tolerates ``school is None`` and
missing models, logging at DEBUG and returning silently. Production callers
get first-class model writes; CI-only callers without the full domain stack
still land their data in cockpit_payload via the wizard writer.

Public API:

* ``apply_palette(school, *, palette_key, primary_color_hex, secondary_color_hex, type_scale_anchor)``
* ``install_brand_assets(school, *, logo, favicon, social_share_image, alt_text)``
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

__all__ = ["apply_palette", "install_brand_assets"]


def _get_or_create_brand_profile(school: Any):
    """Return BrandProfile for school, creating if absent. ``None`` on failure."""
    try:
        from apps.siteconfig.models_global_experience import BrandProfile
    except ImportError:
        logger.debug("apply_palette: BrandProfile model unavailable")
        return None
    if school is None or getattr(school, "pk", None) is None:
        return None
    profile, _ = BrandProfile.objects.get_or_create(school=school)
    return profile


def apply_palette(
    school: Any,
    *,
    palette_key: str | None = None,
    primary_color_hex: str | None = None,
    secondary_color_hex: str | None = None,
    type_scale_anchor: str | None = None,
) -> bool:
    """Persist palette selection into BrandProfile + tokens JSON.

    Returns ``True`` on successful write, ``False`` on no-op / missing model.
    Field-by-field — empty/None inputs skip rather than clobber.
    """
    profile = _get_or_create_brand_profile(school)
    if profile is None:
        return False

    update_fields: list[str] = []
    if primary_color_hex:
        profile.primary_color = primary_color_hex
        update_fields.append("primary_color")
    if secondary_color_hex:
        profile.secondary_color = secondary_color_hex
        update_fields.append("secondary_color")

    tokens = profile.tokens or {}
    if not isinstance(tokens, dict):
        tokens = {}
    if palette_key:
        tokens["palette_key"] = palette_key
    if type_scale_anchor:
        tokens["type_scale_anchor"] = type_scale_anchor
    if palette_key or type_scale_anchor:
        profile.tokens = tokens
        update_fields.append("tokens")

    if not update_fields:
        return False

    update_fields.append("updated_at")
    try:
        profile.save(update_fields=update_fields)
    except Exception as exc:  # noqa: BLE001
        logger.warning("apply_palette: BrandProfile save failed: %s", exc)
        return False
    return True


def install_brand_assets(
    school: Any,
    *,
    logo: Any = None,
    favicon: Any = None,
    social_share_image: Any = None,
    alt_text: str | None = None,
) -> bool:
    """Persist brand-asset metadata into BrandProfile.assets JSON.

    File handling is left to the storage layer — this helper records the
    filename + size for each provided asset so later sync code can reconcile
    against the storage backend. Empty/None inputs skip.
    """
    profile = _get_or_create_brand_profile(school)
    if profile is None:
        return False

    assets = profile.assets or {}
    if not isinstance(assets, dict):
        assets = {}

    def _asset_meta(value: Any) -> dict[str, Any] | None:
        if value is None:
            return None
        if isinstance(value, str):
            return {"name": value}
        name = getattr(value, "name", None)
        size = getattr(value, "size", None)
        if name is None and size is None:
            return None
        return {"name": name, "size": size}

    changed = False
    for key, value in (
        ("logo", logo),
        ("favicon", favicon),
        ("social_share_image", social_share_image),
    ):
        meta = _asset_meta(value)
        if meta is not None:
            assets[key] = meta
            changed = True
    if alt_text:
        assets["alt_text"] = alt_text
        changed = True

    if not changed:
        return False

    profile.assets = assets
    try:
        profile.save(update_fields=["assets", "updated_at"])
    except Exception as exc:  # noqa: BLE001
        logger.warning("install_brand_assets: BrandProfile save failed: %s", exc)
        return False
    return True
