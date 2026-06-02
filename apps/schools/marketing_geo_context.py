"""
Geopolitical context for marketing templates (RUNMYCAMPUS-GLOCAL).

Exposes ``request.geo_context`` and template context ``geo`` without a separate
glocal_kernel app — built on siteconfig country resolution.
"""
from __future__ import annotations

from typing import Any


def build_geo_context(request) -> dict[str, Any]:
    # Lazy import avoids circular init with marketing template processors at Django startup.
    from apps.schools.marketing_media_matrix import (
        apm_icons_for_country,
        apm_primary_static_for_country,
        assets_for_country,
        loop_bucket_for_country,
    )
    try:
        from apps.siteconfig.country_localization_service import resolve_country_for_request
        from apps.siteconfig.localization_context_processor import localization_context

        cc = resolve_country_for_request(request) or ""
        loc = localization_context(request).get("localization") or {}
    except Exception:  # noqa: BLE001
        cc = ""
        loc = {}

    direction = "rtl" if loc.get("is_rtl") else "ltr"
    lang = (loc.get("language_code") or "en").strip()
    locale = f"{lang}-{cc}" if cc else lang

    currency = str(loc.get("currency_code") or "USD")
    symbols = {"USD": "$", "EUR": "€", "GBP": "£", "NGN": "₦", "BRL": "R$", "INR": "₹", "SAR": "ر.س", "AED": "د.إ", "KES": "KSh", "XOF": "CFA", "XAF": "FCFA"}
    return {
        "country_code": cc or "US",
        "locale": locale,
        "direction": direction,
        "currency": currency,
        "currency_symbol": symbols.get(currency, currency),
        "loop_bucket": loop_bucket_for_country(cc),
        "assets": assets_for_country(cc),
        "apm_icons": apm_icons_for_country(cc),
        "apm_image": apm_primary_static_for_country(cc),
        "is_rtl": direction == "rtl",
    }


def marketing_geo_context(request) -> dict[str, Any]:
    geo = build_geo_context(request)
    request.geo_context = geo  # type: ignore[attr-defined]
    return {"geo": geo, "geo_context": geo}
