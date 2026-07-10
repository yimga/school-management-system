from __future__ import annotations

from typing import Any

from django.db import DatabaseError

from apps.brand_experience.models import BrandProfile, BrandSettings
from apps.brand_experience.experience_packs import resolve_experience_theme_pack

from .brand_registry import resolve_global_brand_context


OPTIONAL_BRANDING_ERRORS = (AttributeError, DatabaseError, TypeError, ValueError)


def _school_theme_pack(school, site):
    if school:
        pack = resolve_experience_theme_pack(school=school)
        if pack is not None:
            return pack
    if school and getattr(school, "theme_pack_id", None):
        return getattr(school, "theme_pack", None)
    if site and hasattr(site, "get_portal_theme"):
        try:
            return site.get_portal_theme()
        except OPTIONAL_BRANDING_ERRORS:
            return None
    return None


def _branding_metadata(school) -> dict[str, Any]:
    payload = getattr(school, "branding_metadata", None) or {}
    return payload if isinstance(payload, dict) else {}


def _theme_tokens(pack) -> dict[str, Any]:
    if not pack:
        return {}
    return {
        "primary_color": getattr(pack, "primary_color", "") or "",
        "accent_color": getattr(pack, "accent_color", "") or "",
        "background_color": getattr(pack, "background_color", "") or "",
        "font_family": getattr(pack, "font_family", "") or "",
        "logo_url": getattr(getattr(pack, "logo", None), "url", "")
        if getattr(pack, "logo", None)
        else "",
        "login_background_url": getattr(
            getattr(pack, "background_image", None), "url", ""
        )
        if getattr(pack, "background_image", None)
        else "",
    }


def resolve_brand_profile(*, school=None, site=None) -> dict[str, Any]:
    """
    Resolve tenant runtime branding from one source of truth with controlled fallbacks.
    Precedence:
    1. BrandProfile
    2. Legacy BrandSettings
    3. School branding fields / branding_metadata
    4. ThemePack tokens
    5. Site settings / global defaults
    """
    site_primary = getattr(site, "primary_color", None) or "#0d6efd"
    site_accent = getattr(site, "accent_color", None) or "#198754"
    theme_pack = _school_theme_pack(school, site)
    theme_tokens = _theme_tokens(theme_pack)
    metadata = _branding_metadata(school)
    global_brand = resolve_global_brand_context(school=school) if school else {}
    profile = None
    legacy = None
    if school is not None:
        try:
            profile = (
                getattr(school, "brand_profile", None)
                or BrandProfile.objects.filter(school=school).first()
            )
        except OPTIONAL_BRANDING_ERRORS:
            profile = None
        try:
            legacy = (
                getattr(school, "brand_settings", None)
                or BrandSettings.objects.filter(school=school).first()
            )
        except OPTIONAL_BRANDING_ERRORS:
            legacy = None

    primary_color = (
        getattr(profile, "primary_color", None)
        or getattr(legacy, "primary_color", None)
        or metadata.get("primary")
        or getattr(school, "primary_color", None)
        or theme_tokens.get("primary_color")
        or site_primary
    )
    accent_color = (
        getattr(profile, "accent_color", None)
        or getattr(legacy, "accent_color", None)
        or metadata.get("accent")
        or getattr(school, "accent_color", None)
        or theme_tokens.get("accent_color")
        or site_accent
    )
    font_family = (
        getattr(profile, "font_family", None)
        or metadata.get("font")
        or theme_tokens.get("font_family")
        or getattr(site, "secondary_font", None)
        or ""
    )
    logo_url = (
        # Inline data URI from the Day-1 logo upload wins — it renders on any
        # host without media serving (survives ephemeral disk / no object
        # storage), which is why a freshly uploaded logo now actually shows.
        metadata.get("logo_data_uri")
        or getattr(profile, "logo_url", None)
        or getattr(legacy, "logo_url", None)
        or getattr(school, "logo_url", None)
        or theme_tokens.get("logo_url")
        or ""
    )
    login_background_url = (
        getattr(profile, "login_background_url", None)
        or getattr(school, "wallpaper_url", None)
        or theme_tokens.get("login_background_url")
        or ""
    )
    favicon_url = getattr(profile, "favicon_url", None) or ""
    resolved = {
        "logo_url": logo_url or "",
        "logo_dark_url": getattr(profile, "logo_dark_url", None) or "",
        "favicon_url": favicon_url,
        "tagline": getattr(profile, "tagline", None)
        or getattr(site, "tagline", None)
        or "",
        "primary_color": primary_color or "#0d6efd",
        "secondary_color": getattr(profile, "secondary_color", None) or "",
        "accent_color": accent_color or "#198754",
        "font_family": font_family or "",
        "login_background_url": login_background_url or "",
        "portal_visual": getattr(profile, "portal_visual", None) or "",
        "email_template": getattr(profile, "email_template", None) or "",
        "pdf_template": getattr(profile, "pdf_template", None) or "",
        "certificate_template": getattr(profile, "certificate_template", None) or "",
        "custom_css": getattr(profile, "custom_css", None)
        or getattr(legacy, "custom_css", None)
        or "",
        "tokens": {},
        "assets": getattr(profile, "assets", None) or {},
        "templates": getattr(profile, "templates", None) or {},
        "theme_pack_id": getattr(theme_pack, "id", None),
        "theme_pack_slug": getattr(theme_pack, "slug", "") if theme_pack else "",
        "source": "brand_profile"
        if profile
        else ("brand_settings" if legacy else "school"),
        "country_code": getattr(school, "canonical_country_code", "") if school else "",
        "labels_map": (global_brand.get("labels_map") or {})
        if isinstance(global_brand, dict)
        else {},
    }
    tokens = {}
    tokens.update(theme_tokens)
    if metadata:
        tokens.update(metadata)
    profile_tokens = getattr(profile, "tokens", None) or {}
    if isinstance(profile_tokens, dict):
        tokens.update(profile_tokens)
    tokens.setdefault("primary_color", resolved["primary_color"])
    tokens.setdefault("accent_color", resolved["accent_color"])
    if resolved["font_family"]:
        tokens.setdefault("font_family", resolved["font_family"])
    resolved["tokens"] = tokens
    return resolved


def brand_css_vars(brand: dict[str, Any]) -> str:
    tokens = dict(brand.get("tokens") or {})
    parts = []
    primary = (
        tokens.get("primary")
        or tokens.get("primary_color")
        or brand.get("primary_color")
    )
    accent = (
        tokens.get("accent") or tokens.get("accent_color") or brand.get("accent_color")
    )
    font_family = (
        tokens.get("font") or tokens.get("font_family") or brand.get("font_family")
    )
    if primary:
        primary_str = str(primary).strip()
        parts.append(f"--primary: {primary_str};")
        # Adaptive on-brand text: dark ink on a light brand, light ink on a dark
        # brand, so white-on-brand headers never wash out. Sites already consume
        # var(--text-on-brand, #fff); this makes the variable actually resolve.
        from apps.siteconfig.contrast_guard import text_color_for_background

        parts.append(f"--text-on-brand: {text_color_for_background(primary_str)};")
    if accent:
        parts.append(f"--accent: {str(accent).strip()};")
    if font_family:
        parts.append(f"--school-font: {str(font_family).strip()};")
    return " ".join(parts)
