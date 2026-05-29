"""Continent + wave helpers for the global governance program (stdlib + geonamescache)."""

from __future__ import annotations

from functools import lru_cache
from typing import Any

_CONTINENT_CODE_TO_WAVE = {
    "AF": ("Africa", "W-Africa"),
    "AS": ("Asia", "W-Asia"),
    "EU": ("Europe", "W-Europe"),
    "NA": ("Americas", "W-Americas"),
    "SA": ("Americas", "W-Americas"),
    "OC": ("Oceania", "W-Oceania"),
    "AN": ("Antarctica", "W-Territories"),
}

# ISO codes absent from geonamescache but present in pycountry.
_ALPHA2_CONTINENT_OVERRIDES: dict[str, tuple[str, str]] = {
    "AQ": ("Antarctica", "W-Territories"),
    "BV": ("Antarctica", "W-Territories"),
    "GS": ("Antarctica", "W-Territories"),
    "HM": ("Oceania", "W-Oceania"),
    "TF": ("Africa", "W-Territories"),
    "UM": ("Oceania", "W-Oceania"),
}


@lru_cache(maxsize=1)
def _geonames_by_iso2() -> dict[str, dict[str, Any]]:
    try:
        import geonamescache
    except ImportError:
        return {}
    gc = geonamescache.GeonamesCache()
    return {str(row.get("iso") or "").upper(): row for row in gc.get_countries().values()}


def continent_and_wave_for_alpha2(alpha2: str) -> tuple[str, str]:
    code = (alpha2 or "").strip().upper()
    if code in _ALPHA2_CONTINENT_OVERRIDES:
        return _ALPHA2_CONTINENT_OVERRIDES[code]
    row = _geonames_by_iso2().get(code) or {}
    continent_code = str(row.get("continentcode") or "OC").upper()
    continent, wave = _CONTINENT_CODE_TO_WAVE.get(continent_code, ("Oceania", "W-Oceania"))
    # Dependent territories without sovereign UN membership often map to W-Territories.
    if code in _TERRITORY_ALPHA2:
        return continent, "W-Territories"
    return continent, wave


# Non-sovereign / dependent ISO codes (T3 research tier baseline).
_TERRITORY_ALPHA2 = frozenset(
    {
        "AI", "AQ", "AS", "AW", "AX", "BL", "BM", "BQ", "BV", "CC", "CK", "CW",
        "CX", "EH", "FK", "FO", "GF", "GG", "GI", "GL", "GP", "GU", "HK", "HM",
        "IM", "IO", "JE", "KY", "MC", "MF", "MO", "MP", "MQ", "MS", "NC", "NF",
        "NU", "PF", "PM", "PN", "PR", "RE", "SH", "SJ", "SX", "TC", "TF", "TK",
        "TV", "UM", "VG", "VI", "WF", "YT",
    }
)


def is_likely_territory(alpha2: str) -> bool:
    return (alpha2 or "").strip().upper() in _TERRITORY_ALPHA2


def research_tier_for(alpha2: str, *, sovereign: bool) -> str:
    if not sovereign or is_likely_territory(alpha2):
        return "T3"
    if alpha2 in _T1_DEEP_ALPHA2:
        return "T1"
    return "T2"


_T1_DEEP_ALPHA2 = frozenset(
    {
        "CM", "NG", "KE", "GH", "ZA", "SN", "CI", "TZ", "UG", "RW", "ET", "EG",
        "US", "CA", "GB", "FR", "DE", "ES", "IT", "IN", "CN", "JP", "BR", "MX",
        "AU", "NZ", "AE", "SA", "QA", "SG", "MY", "PH", "ID", "PK", "BD", "TR",
        "NL", "BE", "CH", "AT", "SE", "NO", "DK", "FI", "PL", "PT", "IE", "IL",
        "AR", "CL", "CO", "PE",
    }
)
