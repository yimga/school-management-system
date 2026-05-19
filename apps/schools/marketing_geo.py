"""Marketing geo copy helpers — hero taglines and proof lines by country."""
from __future__ import annotations

# Illustrative campus names for logo carousel (not customer claims).
MARKETING_CAROUSEL_ITEMS = (
    "Cedar Ridge Academy",
    "Riverbend Network",
    "Beacon Heights",
    "Hollow Creek",
    "Sunnyside International",
    "Willow Field College",
)

MARKETING_PROOF_QUOTE = {
    "quote": (
        "We stopped reconciling fees in spreadsheets the week we switched. "
        "Parents pay on the link they already have — our bursar reviews, not re-enters."
    ),
    "name": "Amara O.",
    "role": "Bursar, multi-campus group",
}

_GEO_TAGLINES: dict[str, str] = {
    "US": "The operating system for U.S. school districts",
    "CA": "The operating system for Canadian K–12 networks",
    "NG": "The operating system for Nigerian school groups",
    "CM": "The operating system for Francophone school networks",
    "GB": "The operating system for UK independent schools",
    "GH": "The operating system for Ghanaian school networks",
    "KE": "The operating system for Kenyan school networks",
    "ZA": "The operating system for South African schools",
    "IN": "The operating system for international schools in India",
    "AU": "The operating system for Australian colleges & schools",
    "FR": "The operating system for French-language school networks",
}


def marketing_geo_tagline(country_code: str, country_name: str = "") -> str:
    code = (country_code or "").strip().upper()[:2]
    if code in _GEO_TAGLINES:
        return _GEO_TAGLINES[code]
    if country_name:
        return f"The operating system for schools in {country_name}"
    return "The operating system for modern K–12 campuses worldwide"
