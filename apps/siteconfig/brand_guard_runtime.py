"""
Platform-wide WCAG AAA brand guard — remediate primary/accent before persist and render.

Applies remediate_brand_hex_on_background on light (#ffffff) and dark (#0f172a) surfaces
per THEME_SYSTEM.md v3 effective-theme contract (System → light or dark, never raw
data-theme="system").
"""

from __future__ import annotations

from typing import Any

from apps.siteconfig.contrast_guard import remediate_brand_hex_on_background

LIGHT_SURFACE = "#ffffff"
DARK_SURFACE = "#0f172a"
DEFAULT_MIN_RATIO = 7.0

_BRAND_FIELDS = ("primary_color", "accent_color")


def _remediate_hex_for_surface(
    hex_value: str,
    surface_hex: str,
    *,
    min_ratio: float,
) -> tuple[str, bool]:
    """Remediate brand for one effective surface (v3: System → light OR dark, not both at once)."""
    value = (hex_value or "").strip()
    if not value:
        return value, False
    result = remediate_brand_hex_on_background(value, surface_hex, min_ratio=min_ratio)
    remediated = (result.get("remediated_hex") or value).strip()
    adjusted = bool(result.get("adjusted")) or remediated.lower() != value.lower()
    return remediated, adjusted


def _remediate_hex_for_surfaces(hex_value: str, *, min_ratio: float) -> tuple[str, bool]:
    """
    Persist-time guard: tenants default to light effective theme (TENANT_FORCE_LIGHT_THEME).

    Dark-mode readability is handled by semantic tokens + dark-mode-safety-net.css;
  a single brand hex cannot simultaneously meet 7:1 on #fff and #0f172a.
    """
    return _remediate_hex_for_surface(hex_value, LIGHT_SURFACE, min_ratio=min_ratio)


def guard_brand_hex_fields(
    instance: Any,
    *,
    min_ratio: float = DEFAULT_MIN_RATIO,
    fields: tuple[str, ...] = _BRAND_FIELDS,
) -> dict[str, bool]:
    """
    Mutate brand color fields on instance when contrast fails AAA on either surface.

    Returns per-field adjusted flags for operator UI (`adjusted: true`).
    """
    flags: dict[str, bool] = {}
    for name in fields:
        raw = getattr(instance, name, None)
        if not raw or not str(raw).strip():
            continue
        remediated, was_adjusted = _remediate_hex_for_surfaces(
            str(raw), min_ratio=min_ratio
        )
        if was_adjusted and remediated:
            setattr(instance, name, remediated)
        flags[name] = was_adjusted
    return flags


def guard_brand_dict(
    brand: dict[str, Any] | None,
    *,
    min_ratio: float = DEFAULT_MIN_RATIO,
    effective_surface: str = "light",
) -> tuple[dict[str, Any], bool]:
    """
    Return copy of brand dict with guarded primary/accent; second value is any_adjusted.

    effective_surface: ``light`` or ``dark`` — matches v3 effective theme for render-time guard.
    """
    surface = (
        DARK_SURFACE
        if str(effective_surface or "light").strip().lower() == "dark"
        else LIGHT_SURFACE
    )
    payload = dict(brand or {})
    any_adjusted = False
    for key in _BRAND_FIELDS:
        raw = payload.get(key)
        if not raw:
            continue
        remediated, was_adjusted = _remediate_hex_for_surface(
            str(raw), surface, min_ratio=min_ratio
        )
        if was_adjusted:
            any_adjusted = True
        payload[key] = remediated
    return payload, any_adjusted
