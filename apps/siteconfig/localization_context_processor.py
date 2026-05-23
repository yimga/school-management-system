"""
Wave 2 (v3.62.5) — Localization context processor.

Emits the user's effective localization pack into every template context as
``localization``. Templates can then render:

    {{ localization.country_code }}
    {{ localization.week_start }}             # 0..6 (ISO, 0=Sunday)
    {{ localization.date_format }}            # strftime pattern
    {{ localization.currency_code }}          # ISO 4217
    {{ localization.terminology.teacher }}    # locally-recognized word
    {% for cal in localization.calendar_systems %}...{% endfor %}

Templates that don't read `localization` are unaffected. The processor is
defensive — any failure (no GeoIP, malformed seed, missing School FK) lands
the user on the generic-fallback pack and never raises.
"""

from __future__ import annotations

from .country_localization_service import (
    get_languages,
    resolve_country_for_request,
    resolve_country_pack,
    resolve_for_request,
    resolve_language_for_request,
)
from .country_formats_service import (
    address_order_for,
    compose_full_name,
    dial_code_for,
    name_order_for,
    postal_code_label_for,
    region_label_for,
)

# Static cross-country defaults — overridable per-country via CurrencyRegistry
# / LocaleRegistry later (Wave 4). Kept inline here so the context processor
# is dependency-light + boot-safe even when registry tables are empty.
_DEFAULT_CURRENCY_BY_COUNTRY: dict[str, str] = {
    "US": "USD", "CA": "CAD", "GB": "GBP", "IE": "EUR",
    "AU": "AUD", "NZ": "NZD", "JP": "JPY", "KR": "KRW", "CN": "CNY",
    "IN": "INR", "PK": "PKR", "BD": "BDT", "LK": "LKR", "NP": "NPR",
    "FR": "EUR", "DE": "EUR", "ES": "EUR", "IT": "EUR", "NL": "EUR",
    "BE": "EUR", "PT": "EUR", "AT": "EUR", "FI": "EUR", "GR": "EUR",
    "SE": "SEK", "NO": "NOK", "DK": "DKK", "PL": "PLN", "CZ": "CZK",
    "HU": "HUF", "RO": "RON", "BG": "BGN", "RU": "RUB", "UA": "UAH",
    "TR": "TRY", "CH": "CHF",
    "BR": "BRL", "MX": "MXN", "AR": "ARS", "CL": "CLP", "CO": "COP",
    "PE": "PEN", "VE": "VES", "UY": "UYU", "BO": "BOB", "PY": "PYG",
    "NG": "NGN", "KE": "KES", "GH": "GHS", "ZA": "ZAR", "EG": "EGP",
    "MA": "MAD", "ET": "ETB", "TZ": "TZS", "UG": "UGX", "DZ": "DZD",
    "TN": "TND", "AO": "AOA", "MZ": "MZN", "CM": "XAF", "SN": "XOF",
    "CI": "XOF", "BJ": "XOF", "BF": "XOF", "ML": "XOF", "NE": "XOF",
    "TG": "XOF", "GA": "XAF", "TD": "XAF", "CG": "XAF", "CF": "XAF",
    "GQ": "XAF",
    "AE": "AED", "SA": "SAR", "IL": "ILS", "QA": "QAR", "KW": "KWD",
    "BH": "BHD", "OM": "OMR", "LB": "LBP", "JO": "JOD", "IQ": "IQD",
    "IR": "IRR", "YE": "YER", "SY": "SYP",
    "ID": "IDR", "MY": "MYR", "PH": "PHP", "SG": "SGD", "TH": "THB",
    "VN": "VND", "MM": "MMK", "KH": "KHR", "LA": "LAK", "BN": "BND",
}

# Per-country date format — overridable. Sensible regional defaults.
_DEFAULT_DATE_FORMAT_BY_COUNTRY: dict[str, str] = {
    "US": "%m/%d/%Y",
    "CA": "%Y-%m-%d",
    # British Commonwealth + most of the world: DD/MM/YYYY
}

_RTL_COUNTRIES: frozenset[str] = frozenset({
    "AE", "SA", "IL", "QA", "KW", "BH", "OM", "JO", "LB", "IQ", "IR",
    "SY", "YE", "PS", "EG", "MA", "DZ", "TN", "LY", "SD", "MR",
    "PK",  # Urdu is RTL though signage often LTR mixed
    "AF",  # Pashto / Dari RTL
})


def _calendar_default(pack: dict) -> dict:
    """Return the primary/default calendar from the pack (or first entry)."""
    cals = list(pack.get("calendar_systems") or [])
    for c in cals:
        if c.get("is_default"):
            return c
    return cals[0] if cals else {}


def _currency_code(country_code: str) -> str:
    return _DEFAULT_CURRENCY_BY_COUNTRY.get(country_code, "USD")


def _date_format(country_code: str) -> str:
    return _DEFAULT_DATE_FORMAT_BY_COUNTRY.get(country_code, "%d/%m/%Y")


def localization_context(request) -> dict:
    """Emit `localization` for every template render.

    Returns a dict with this shape (always populated, never raises)::

        localization = {
            "country_code":    "NG",
            "calendar_systems": [...full list...],
            "default_calendar": {...primary one...},
            "school_types":    [...full list...],
            "education_levels":[...full list...],
            "terminology":     {teacher: ..., principal: ..., ...},
            "week_start":      1,                 # 0=Sun..6=Sat
            "date_format":     "%d/%m/%Y",       # strftime pattern
            "currency_code":   "NGN",
            "is_rtl":          False,
            "_source":         "country:NG",
        }
    """
    try:
        cc = resolve_country_for_request(request)
        # Wave 6 (v3.62.8): resolve language and use language overlay when
        # applicable. Monolingual countries get the baseline pack; multilingual
        # countries get the per-language education-system overlay.
        pack = resolve_for_request(request)
        cal = _calendar_default(pack)
        lang_code = (pack.get("language_code") or "").strip().lower()
        loc = {
            "country_code":     cc,
            "language_code":    lang_code,
            "language_native":  str(pack.get("language_native_name") or ""),
            "language_region":  str(pack.get("language_region") or ""),
            "system_name":      str(pack.get("system_name") or ""),
            "languages":        [
                {
                    "code": str(l.get("code") or "").lower(),
                    "native_name": str(l.get("native_name") or ""),
                    "is_official": bool(l.get("is_official")),
                    "is_default": bool(l.get("is_default")),
                    "region": str(l.get("region") or ""),
                    "has_education_system_overlay": bool(l.get("education_system")),
                }
                for l in (pack.get("languages") or [])
                if isinstance(l, dict)
            ],
            "calendar_systems": list(pack.get("calendar_systems") or []),
            "default_calendar": cal,
            "school_types":     list(pack.get("school_types") or []),
            "education_levels": list(pack.get("education_levels") or []),
            "terminology":      dict(pack.get("terminology") or {}),
            "week_start":       int(cal.get("week_start") or 1),
            "date_format":      _date_format(cc),
            "currency_code":    _currency_code(cc),
            "is_rtl":           cc in _RTL_COUNTRIES,
            # Wave 4: format helpers — emit alongside calendar/terminology so
            # forms / cards / invoices don't need to import the helpers.
            "name_order":       name_order_for(cc),
            "address_order":    list(address_order_for(cc)),
            "dial_code":        dial_code_for(cc),
            "postal_code_label": postal_code_label_for(cc),
            "region_label":     region_label_for(cc),
            "_source":          pack.get("_source", ""),
        }
    except Exception:  # noqa: BLE001 — never break template rendering
        loc = {
            "country_code": "", "language_code": "",
            "language_native": "", "language_region": "", "system_name": "",
            "languages": [],
            "calendar_systems": [], "default_calendar": {},
            "school_types": [], "education_levels": [], "terminology": {},
            "week_start": 1, "date_format": "%d/%m/%Y", "currency_code": "USD",
            "is_rtl": False,
            "name_order": "given-family",
            "address_order": ["street", "city", "region", "postal_code", "country"],
            "dial_code": "", "postal_code_label": "Postal code",
            "region_label": "Region",
            "_source": "context-processor-error",
        }
    return {"localization": loc}
