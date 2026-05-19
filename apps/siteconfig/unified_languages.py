"""
Single language switcher contract: Django ``LANGUAGES`` is canonical.

``TranslationManager`` JSON overlays supplement runtime strings for the six
legacy JSON locales; all UI switchers use ``get_unified_language_choices()``.
"""

from __future__ import annotations

from django.conf import settings

# Map Django language codes → gettext locale directory names.
DJANGO_TO_GETTEXT_LOCALE = {
    "pt-br": "pt_BR",
    "zh-hans": "zh_Hans",
    "zh-hant": "zh_Hant",
}

GETTEXT_TO_DJANGO_LOCALE = {v: k for k, v in DJANGO_TO_GETTEXT_LOCALE.items()}


def get_unified_language_choices() -> list[tuple[str, str]]:
    """Return [(code, display)] from settings.LANGUAGES — single switcher SOT."""
    return list(getattr(settings, "LANGUAGES", []) or [("en", "English")])


def unified_language_codes() -> frozenset[str]:
    return frozenset(code for code, _ in get_unified_language_choices())


def normalize_language_code(code: str | None) -> str:
    """Normalize user/cookie code to a registered Django language code."""
    raw = (code or "").strip().lower().replace("_", "-")
    if not raw:
        return "en"
    codes = {c.lower(): c for c, _ in get_unified_language_choices()}
    if raw in codes:
        return codes[raw]
    if raw == "pt" and "pt-br" in codes:
        return codes["pt-br"]
    return "en"


def gettext_locale_for_django(code: str) -> str:
    """Directory name under locale/ for a Django language code."""
    norm = normalize_language_code(code)
    return DJANGO_TO_GETTEXT_LOCALE.get(norm, norm.replace("-", "_"))
