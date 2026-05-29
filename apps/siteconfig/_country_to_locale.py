"""v4.00.32 — country-code → default locale map.

Used when a tenant has no explicit user locale preference, so the platform
can still pick a sensible default (Francophone West Africa → fr, Maghreb →
ar+fr, Lusophone → pt) instead of always defaulting to English.

The map intentionally returns Django LANGUAGE_CODE strings — the cmdk
`resolveSpeechLang()` mapper then translates that to BCP-47 for the Web
Speech API.
"""
from __future__ import annotations


COUNTRY_TO_LOCALE: dict[str, str] = {
    # Anglophone Africa
    "GH": "en", "NG": "en", "KE": "en", "UG": "en", "TZ": "en",
    "ZA": "en", "ZW": "en", "ZM": "en", "GM": "en", "SL": "en",
    "LR": "en", "MW": "en", "BW": "en", "NA": "en", "LS": "en",
    "RW": "en",   # English official since 2008
    # Francophone Africa
    "CM": "fr",   # bilingual but French majority
    "SN": "fr", "CI": "fr", "TG": "fr", "BJ": "fr", "BF": "fr",
    "ML": "fr", "NE": "fr", "TD": "fr", "GA": "fr", "CG": "fr",
    "CD": "fr", "MG": "fr", "DJ": "fr", "GN": "fr",
    "MR": "ar",  # Arabic primary, French co-official
    # Maghreb — Arabic primary
    "MA": "ar", "TN": "ar", "DZ": "ar", "LY": "ar", "EG": "ar",
    # Horn of Africa
    "ET": "am", "ER": "en", "SO": "en",
    # Lusophone Africa
    "MZ": "pt", "AO": "pt", "GW": "pt", "CV": "pt", "ST": "pt",
    # Default English-speaking world
    "US": "en", "GB": "en", "CA": "en", "AU": "en", "NZ": "en",
    "IE": "en",
    # Europe big locales
    "FR": "fr", "BE": "fr", "CH": "fr", "ES": "es", "PT": "pt",
    "IT": "it", "DE": "de", "AT": "de", "NL": "nl",
    # LatAm
    "BR": "pt", "MX": "es", "AR": "es", "CL": "es", "CO": "es",
    "PE": "es", "EC": "es", "VE": "es", "UY": "es", "PY": "es",
    "BO": "es", "CR": "es", "PA": "es", "DO": "es",
    # MENA + Asia
    "SA": "ar", "AE": "ar", "QA": "ar", "BH": "ar", "OM": "ar",
    "KW": "ar", "JO": "ar", "LB": "ar", "SY": "ar", "IQ": "ar",
    "YE": "ar", "PS": "ar",
    "CN": "zh", "TW": "zh", "HK": "zh", "JP": "ja", "KR": "ko",
    "IN": "en", "PK": "en", "BD": "en", "LK": "en",
    "ID": "id", "MY": "en", "SG": "en", "PH": "en", "VN": "vi",
    "TH": "th",
}


def locale_for_country(country_code: str) -> str:
    """Return the default LANGUAGE_CODE for a country. Empty string when unknown."""
    return COUNTRY_TO_LOCALE.get((country_code or "").upper(), "")


def best_locale(*, user_locale: str = "", school_country: str = "", request_locale: str = "") -> str:
    """Pick the best locale: user pref → Django request → school country fallback.

    Used by the cmdk + form-validator layers to drive Web Speech language
    selection without surprising the operator with US English when their
    tenant is, say, a Cameroon Francophone lycée.
    """
    for candidate in (user_locale, request_locale):
        c = (candidate or "").strip().split("-")[0].lower()
        if c and c not in ("en",):
            # Trust an explicit non-English user/request locale.
            return c
    if school_country:
        guess = locale_for_country(school_country)
        if guess:
            return guess
    # Fall back to user/request English (or empty).
    return (user_locale or request_locale or "en").strip().split("-")[0].lower() or "en"
