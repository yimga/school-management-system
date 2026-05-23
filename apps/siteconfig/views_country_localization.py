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
    normalize_country_code,
    resolve_country_pack,
)


@require_GET
@cache_control(public=True, max_age=86_400)  # 24h — seed only changes on deploys.
def country_localization_pack(request: HttpRequest, country_code: str) -> JsonResponse:
    """Return the localization pack for `country_code`.

    Response shape::

        {
          "country_code": "NG",
          "calendar_systems": [
            {"code": "ng-3-term", "label": "3 Terms", "sub": "First / Second / Third",
             "term_count": 3, "is_default": true, ...},
            ...
          ],
          "school_types": [
            {"code": "nursery", "label": "Nursery", "glyph": "...", "primary_sector": "early_childhood", "typical_ages": "0-4"},
            {"code": "primary", "label": "Primary", ...},
            ...
          ],
          "education_levels": [...],
          "terminology": {"teacher": "...", "principal": "...", ...},
          "_source": "country:NG"     # debug — which lookup matched
        }

    Always 200 with a valid pack — unknown countries get the generic-fallback
    pack. The `_source` key indicates which level matched (country / regional /
    generic-fallback) for ops debugging.
    """
    cc = normalize_country_code(country_code)
    pack = resolve_country_pack(cc)
    out = {
        "country_code": cc,
        "calendar_systems": list(pack.get("calendar_systems") or []),
        "school_types": list(pack.get("school_types") or []),
        "education_levels": list(pack.get("education_levels") or []),
        "terminology": dict(pack.get("terminology") or {}),
        "_source": pack.get("_source", ""),
    }
    return JsonResponse(out)
