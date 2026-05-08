"""Per-country phone-number placeholder + dial code lookup.

Keeps form widgets out of the ``+237 6XX XXX XXX`` Cameroon-only state.
Looked up by ISO 3166-1 alpha-2; fall back to a generic international hint
when the corridor isn't enumerated.
"""

from __future__ import annotations

from typing import Final

# (dial_code_with_plus, placeholder)
PHONE_FORMATS: Final[dict[str, tuple[str, str]]] = {
    "CM": ("+237", "+237 6XX XXX XXX"),
    "NG": ("+234", "+234 8XX XXX XXXX"),
    "GH": ("+233", "+233 24 XXX XXXX"),
    "KE": ("+254", "+254 7XX XXX XXX"),
    "UG": ("+256", "+256 7XX XXX XXX"),
    "TZ": ("+255", "+255 7XX XXX XXX"),
    "RW": ("+250", "+250 78X XXX XXX"),
    "ZA": ("+27", "+27 8X XXX XXXX"),
    "CI": ("+225", "+225 07 XX XXX XXX"),
    "SN": ("+221", "+221 7X XXX XX XX"),
    "CD": ("+243", "+243 8X XXX XXXX"),
    "GB": ("+44", "+44 7XXX XXXXXX"),
    "US": ("+1", "+1 (XXX) XXX-XXXX"),
    "FR": ("+33", "+33 6 XX XX XX XX"),
    "DE": ("+49", "+49 1XX XXXXXXXX"),
    "ES": ("+34", "+34 6XX XX XX XX"),
    "IN": ("+91", "+91 9XXXX XXXXX"),
}

DEFAULT_PLACEHOLDER: Final[str] = "+CC NNN NNN NNNN"
DEFAULT_DIAL_CODE: Final[str] = ""


def phone_placeholder(iso2: str | None) -> str:
    """Return the placeholder string for an ISO2 code.

    Falls back to a neutral international placeholder if unknown.
    """
    code = (iso2 or "").strip().upper()
    if not code:
        return DEFAULT_PLACEHOLDER
    return PHONE_FORMATS.get(code, (DEFAULT_DIAL_CODE, DEFAULT_PLACEHOLDER))[1]


def dial_code(iso2: str | None) -> str:
    """Return the dial code (e.g. ``+237``) for an ISO2 code, or empty."""
    code = (iso2 or "").strip().upper()
    if not code:
        return DEFAULT_DIAL_CODE
    return PHONE_FORMATS.get(code, (DEFAULT_DIAL_CODE, DEFAULT_PLACEHOLDER))[0]


__all__ = ["PHONE_FORMATS", "phone_placeholder", "dial_code"]
