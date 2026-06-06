"""
Shared signup / onboarding localization bootstrap for client adapters.

Embeds the server-rendered country pack + API URL pattern so
``rmc-signup-country-adapter.js`` works offline-first on public signup,
onboarding wizard, and operator rapid-create.
"""

from __future__ import annotations

import json

from django.http import HttpRequest

from apps.siteconfig.country_localization_service import (
    INDIA_STATE_LANGUAGE_MAP,
    normalize_country_code,
)
from apps.siteconfig.platform_surface_config import resolve_api_urls
from apps.siteconfig.signup_migration_recommendations import migration_context_for_country
from apps.siteconfig.views_country_localization import serialize_country_localization_pack

# Tier-1 + high-traffic corridors — prefetched on signup for offline country switching.
SIGNUP_LOCALIZATION_PREFETCH_COUNTRIES: tuple[str, ...] = (
    "US",
    "GB",
    "CM",
    "NG",
    "FR",
    "DE",
    "IN",
    "CN",
    "AU",
    "CA",
    "KE",
    "ZA",
    "BR",
    "MX",
    "SG",
    "AE",
    "SA",
    "JP",
    "KR",
    "PH",
    "PK",
    "BD",
    "GH",
    "CI",
    "SN",
    "ES",
    "IT",
    "NL",
    "BE",
    "CH",
)


def build_signup_localization_bootstrap(
    request: HttpRequest,
    country_code: str,
    country_pack: dict,
    *,
    extra_prefetch: tuple[str, ...] = (),
) -> dict:
    """JSON-safe bootstrap consumed by rmc-signup-country-adapter + prefetch JS."""
    cc = normalize_country_code(country_code)
    pattern = resolve_api_urls(request).get("localization_country") or ""
    prefetch: list[str] = []
    seen: set[str] = set()
    for code in (cc, *extra_prefetch, *SIGNUP_LOCALIZATION_PREFETCH_COUNTRIES):
        norm = normalize_country_code(code)
        if not norm or norm in seen:
            continue
        seen.add(norm)
        prefetch.append(norm)
    return {
        "country_code": cc,
        "pack": serialize_country_localization_pack(cc, country_pack),
        "urls": {"localization_country": pattern},
        "prefetch_countries": prefetch[:32],
        "migration": migration_context_for_country(cc),
        "india_state_language_map": dict(INDIA_STATE_LANGUAGE_MAP),
    }


def signup_localization_json(
    request: HttpRequest,
    country_code: str,
    country_pack: dict,
    *,
    extra_prefetch: tuple[str, ...] = (),
) -> str:
    return json.dumps(
        build_signup_localization_bootstrap(
            request, country_code, country_pack, extra_prefetch=extra_prefetch
        ),
        ensure_ascii=False,
    )


def build_migration_locale_context(
    country_code: str,
    *,
    language_code: str = "",
    language_codes: list[str] | None = None,
    calendar_code: str = "",
    education_cycles: list[str] | None = None,
) -> dict:
    """Locale handoff blob stored on migration_intent + bundle progress_snapshot."""
    from apps.siteconfig.country_localization_service import (
        get_default_calendar_code,
        get_terminology,
        normalize_country_code,
    )

    cc = normalize_country_code(country_code)
    cal = (calendar_code or "").strip() or get_default_calendar_code(cc)
    codes = [str(c).strip().lower()[:16] for c in (language_codes or []) if str(c).strip()]
    primary = (language_code or "").strip()[:16] or (codes[0] if codes else "")
    ctx: dict = {
        "country_code": cc,
        "language_code": primary,
        "primary_language_code": primary,
        "language_codes": codes or ([primary] if primary else []),
        "calendar_code": cal[:48],
        "education_cycles": list(education_cycles or []),
    }
    if cc:
        term_label = str(get_terminology(cc).get("term") or "").strip()
        if term_label:
            ctx["term_label"] = term_label[:120]
    return ctx
