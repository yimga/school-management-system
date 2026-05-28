"""
Read-only localization API for the country-adaptive signup form.

URL: /api/v1/localization/<country_code>/

Returns a JSON pack describing how the school year is structured + what
school-type cards to show + what terminology to render for the specified
country. Used by `static/js/_pages/rmc-signup-country-adapter.js` to
re-render the signup form's calendar cards + school-type cards in place
when the operator changes the country dropdown.

Public, GET-only. Country code is the only input — no PII, no tenant
context required.
"""

from __future__ import annotations

from django.http import HttpRequest, JsonResponse
from django.views.decorators.cache import cache_control
from django.views.decorators.http import require_GET

from .country_localization_service import (
    get_default_language,
    normalize_country_code,
    resolve_country_pack,
    resolve_language_pack,
)


def _serialize_pack(cc: str, pack: dict) -> dict:
    """Project the in-memory pack onto the public JSON shape.

    Strips runtime-only `education_system` blobs from the languages list so
    the wire payload stays compact (per-language overlays land on the
    second API call when the user picks a non-default language).
    """
    out_langs: list[dict] = []
    for lang in (pack.get("languages") or []):
        if not isinstance(lang, dict):
            continue
        out_langs.append({
            "code":         str(lang.get("code") or "").strip().lower(),
            "native_name":  str(lang.get("native_name") or ""),
            "is_official":  bool(lang.get("is_official")),
            "is_default":   bool(lang.get("is_default")),
            "region":       str(lang.get("region") or ""),
            "has_education_system_overlay": bool(lang.get("education_system")),
        })
    return {
        "country_code":     cc,
        "language_code":    pack.get("language_code") or get_default_language(cc),
        "system_name":      str(pack.get("system_name") or ""),
        "calendar_systems": list(pack.get("calendar_systems") or []),
        "school_types":     list(pack.get("school_types") or []),
        "education_levels": list(pack.get("education_levels") or []),
        "terminology":      dict(pack.get("terminology") or {}),
        "languages":        out_langs,
        "_source":          pack.get("_source", ""),
    }


@require_GET
@cache_control(public=True, max_age=86_400)  # 24h — seed only changes on deploys.
def country_localization_pack(request: HttpRequest, country_code: str) -> JsonResponse:
    """Return the localization pack for `country_code`.

    Optional `?lang=<bcp47>` query parameter returns the per-language
    overlay pack (Wave 6) — school_types / education_levels / terminology /
    calendar_systems replaced by the language-region's education system
    when one exists; falls through to the country baseline otherwise.

    Always 200; unknown countries get the generic-fallback pack.
    """
    cc = normalize_country_code(country_code)
    lang = (request.GET.get("lang") or "").strip().lower()
    if lang:
        pack = resolve_language_pack(cc, lang)
    else:
        pack = resolve_country_pack(cc)
    return JsonResponse(_serialize_pack(cc, pack))
