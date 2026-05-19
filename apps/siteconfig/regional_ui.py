"""Regional locale / RTL helpers for shells (North Star SLICE 14).

Does not infer identity beyond UI locale signals already present on tenant/region.
"""

from __future__ import annotations

from typing import Any


def _normalize_locale(code: object | None) -> str:
    raw = str(code or "").strip()
    if not raw:
        return "en"
    return raw.replace("_", "-")


def get_effective_locale_for_school(school) -> str:
    """Resolve locale code string for shells (best-effort)."""
    try:
        from django.utils import translation

        lang = translation.get_language()
        if lang:
            return _normalize_locale(lang)
    except Exception:
        pass
    try:
        from apps.siteconfig.tenant_config import get_tenant_locale

        if school is None:
            return "en"
        tl = get_tenant_locale(school=school)
        loc = (tl or {}).get("locale") if isinstance(tl, dict) else ""
        return _normalize_locale(loc) if loc else "en"
    except Exception:
        return "en"


def is_rtl_locale(locale_code: str | None) -> bool:
    """Treat Arabic/Persian/Hebrew/Urdu families as RTL-first for shell layout."""
    lc = (_normalize_locale(locale_code)).lower()
    prefix = lc.split("-", 1)[0]
    return prefix in ("ar", "he", "fa", "ur")


def get_text_direction_for_school(school, policy_is_rtl: bool = False) -> str:
    if policy_is_rtl:
        return "rtl"
    if is_rtl_locale(get_effective_locale_for_school(school)):
        return "rtl"
    return "ltr"


def get_regional_ui_context(school) -> dict[str, Any]:
    loc = get_effective_locale_for_school(school)
    return {
        "locale": loc,
        "rtl_locale_hint": is_rtl_locale(loc),
    }


def augment_region_shell_context(region_ctx: dict, request) -> dict[str, Any]:
    """Merge ``rmc_*`` keys for templates from existing ``region_settings`` output."""
    from django.utils import translation

    loc = region_ctx.get("default_language") or translation.get_language() or "en"
    loc = _normalize_locale(loc)

    policy_rtl = bool(region_ctx.get("is_rtl"))
    rtl_locale = is_rtl_locale(loc)
    direction = "rtl" if policy_rtl or rtl_locale else "ltr"

    low_bandwidth = False
    try:
        school = getattr(request, "school", None)
        if school is not None:
            from apps.siteconfig.tenant_config import get_tenant_locale

            tl = get_tenant_locale(school=school)
            low_bandwidth = bool(
                tl.get("low_bandwidth")
                or tl.get("offline_mode_default")
                or tl.get("enable_offline_mode")
            )
    except Exception:
        low_bandwidth = False

    return {
        "rmc_locale": loc,
        "rmc_text_direction": direction,
        "rmc_low_bandwidth": low_bandwidth,
        "rmc_regional_ui": {
            "locale": loc,
            "direction": direction,
            "rtl_locale_hint": rtl_locale,
            "policy_rtl": policy_rtl,
            "low_bandwidth": low_bandwidth,
        },
    }
