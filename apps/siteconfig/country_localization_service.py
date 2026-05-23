"""
Country localization service — country-adaptive education-system metadata.

This is the single source of truth for "given a country code, what does the
school year look like and what tiers of schools exist?" Used by:

  - apps.schools.signup_views.signup_school (public /signup/)
  - apps.lifecycle.views_rapid_create.RapidCreateView (operator /super/schools/rapid/)
  - apps.siteconfig.views_country_localization (the /api/v1/localization/<cc>/ endpoint)
  - any future surface that needs to ask "is this country a 3-term country?"

## Resolution order

For a given ISO 3166-1 alpha-2 country code we resolve in this order:

  1. Exact entry in `_seed_country_localization.COUNTRY_LOCALIZATION`
     (hand-researched Tier 1 data — Nigeria, France, India, ...)
  2. Regional default keyed by `COUNTRY_REGIONAL_DEFAULT[code]`
     (e.g. "BJ" -> "africa-francophone" -> use the francophone-Africa default pack)
  3. Hard-coded `_GENERIC_FALLBACK_PACK` below
     (covers totally unknown / blank / malformed country codes)

The seed module is imported lazily so the service is testable + boots even
when the seed file is missing (returns _GENERIC_FALLBACK_PACK universally).

## Display-only contract

Per the v3.62.2 product decision: storage of dates stays Gregorian ISO 8601
across the entire platform. This service supplies *display* and *suggested-
default* metadata only — term names, school-type labels, week-start day,
academic-year-starts-month, RTL flag. Non-Gregorian calendars (Ethiopia,
Iran, Saudi, Israel) carry their locale-native term names but the underlying
storage and querying primitive is still Gregorian.
"""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Lazy seed import. If the seed module is missing or malformed, every country
# falls back to _GENERIC_FALLBACK_PACK so the signup form always works.
# ---------------------------------------------------------------------------

def _load_seed() -> tuple[dict[str, dict], dict[str, dict], dict[str, str]]:
    """Import and validate the seed module.

    Returns three dicts:
      COUNTRY_LOCALIZATION   — alpha-2 code -> full pack
      REGIONAL_DEFAULTS      — region key -> full pack
      COUNTRY_REGIONAL_DEFAULT — alpha-2 code -> region key

    On any failure (file missing, malformed, import error) all three return
    empty dicts. The service then serves _GENERIC_FALLBACK_PACK universally.
    """
    try:
        from . import _seed_country_localization as seed  # type: ignore

        country = getattr(seed, "COUNTRY_LOCALIZATION", None) or {}
        regional = getattr(seed, "REGIONAL_DEFAULTS", None) or {}
        regional_map = getattr(seed, "COUNTRY_REGIONAL_DEFAULT", None) or {}
        if not isinstance(country, dict) or not isinstance(regional, dict):
            logger.warning(
                "country_localization_service: seed module shape unexpected; "
                "falling back to generic-pack universal."
            )
            return ({}, {}, {})
        return (country, regional, regional_map)
    except ImportError:
        return ({}, {}, {})
    except Exception:  # noqa: BLE001 — seed import must never break signup
        logger.exception(
            "country_localization_service: seed import raised; falling back "
            "to generic-pack universal."
        )
        return ({}, {}, {})


# ---------------------------------------------------------------------------
# Generic fallback pack. Boots a sensible 3-term schedule + 5 universal
# school-tier cards. Used when the seed file is missing OR the country code
# has no entry AND no regional default.
# ---------------------------------------------------------------------------

_GENERIC_FALLBACK_PACK: dict[str, Any] = {
    "calendar_systems": [
        {
            "code": "generic-3-term",
            "label": "3 terms (default)",
            "sub": "Autumn / Spring / Summer",
            "term_count": 3,
            "term_names": ["Term 1", "Term 2", "Term 3"],
            "week_start": 1,
            "academic_year_starts_month": 9,
            "is_default": True,
        },
        {
            "code": "generic-2-semester",
            "label": "2 semesters",
            "sub": "Fall / Spring",
            "term_count": 2,
            "term_names": ["Semester 1", "Semester 2"],
            "week_start": 1,
            "academic_year_starts_month": 9,
            "is_default": False,
        },
    ],
    "school_types": [
        {"code": "preschool", "label": "Preschool", "glyph": "\U0001f9f8", "primary_sector": "early_childhood", "typical_ages": "3-5"},
        {"code": "primary",   "label": "Primary",   "glyph": "\U0001f3eb", "primary_sector": "primary",         "typical_ages": "5-11"},
        {"code": "secondary", "label": "Secondary", "glyph": "\U0001f393", "primary_sector": "secondary",       "typical_ages": "11-18"},
        {"code": "k12",       "label": "K-12",      "glyph": "\U0001f392", "primary_sector": "k12",             "typical_ages": "5-18"},
        {"code": "university","label": "University","glyph": "\U0001f3db",  "primary_sector": "higher_ed",       "typical_ages": "18+"},
    ],
    "education_levels": [
        {"code": "generic-pre",  "label": "Pre-K",     "order": 0},
        {"code": "generic-k",    "label": "Kindergarten", "order": 1},
        {"code": "generic-g1",   "label": "Grade 1",   "order": 2},
        {"code": "generic-g6",   "label": "Grade 6",   "order": 7},
        {"code": "generic-g12",  "label": "Grade 12",  "order": 13},
    ],
    "terminology": {
        "teacher":     "Teacher",
        "principal":   "Principal",
        "term":        "Term",
        "report_card": "Report Card",
        "grade_level": "Grade",
    },
    "_source": "generic-fallback",
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def normalize_country_code(value: str | None) -> str:
    """Strip + uppercase + clamp to 2 ASCII letters. Empty string when invalid."""
    out = (value or "").strip().upper()
    if len(out) != 2 or not out.isascii() or not out.isalpha():
        return ""
    return out


@lru_cache(maxsize=512)
def resolve_country_pack(country_code: str | None) -> dict[str, Any]:
    """Return the full localization pack for `country_code`.

    Always returns a complete pack with keys: calendar_systems, school_types,
    education_levels, terminology, _source. Never raises.

    `_source` carries which lookup matched, useful for logging and tests:
      - "country:NG"    — Tier 1 exact match
      - "regional:africa-anglophone" — regional default for country NG
      - "generic-fallback" — fell all the way through
    """
    cc = normalize_country_code(country_code)
    country_map, regional_map, country_region_map = _load_seed()

    # 1. Exact country entry (Tier 1).
    if cc and cc in country_map:
        pack = _coerce_seed_pack(country_map[cc])
        pack["_source"] = f"country:{cc}"
        return pack

    # 2. Regional default for this country code.
    if cc and cc in country_region_map:
        region_key = country_region_map[cc]
        if region_key in regional_map:
            pack = _coerce_seed_pack(regional_map[region_key])
            pack["_source"] = f"regional:{region_key}"
            return pack

    # 3. Generic catch-all from the seed (if present), else hard-coded.
    if "generic" in regional_map:
        pack = _coerce_seed_pack(regional_map["generic"])
        pack["_source"] = "regional:generic"
        return pack

    return dict(_GENERIC_FALLBACK_PACK)


def _coerce_seed_pack(raw: dict[str, Any]) -> dict[str, Any]:
    """Normalize a raw seed entry into the public pack shape.

    The seed file uses richer per-country dicts:

        {
          "calendar_system": {...single object...},
          "school_types":     [...],
          "education_levels": [...],
          "terminology":      {...},
        }

    The public pack shape wraps `calendar_system` into a one-element
    `calendar_systems` list (so the UI can offer alternatives — typically
    the default + 1-2 variants like 'British 3-term half-terms'). Country
    entries can also pre-supply `calendar_alternatives: [...]` which get
    appended.

    Never raises. Missing keys fall through to the generic-pack default
    for that field.
    """
    if not isinstance(raw, dict):
        return dict(_GENERIC_FALLBACK_PACK)

    out: dict[str, Any] = {}

    # Calendar systems — accept either `calendar_systems` (list) OR
    # `calendar_system` (single) + optional `calendar_alternatives` (list).
    if isinstance(raw.get("calendar_systems"), list) and raw["calendar_systems"]:
        out["calendar_systems"] = list(raw["calendar_systems"])
    elif isinstance(raw.get("calendar_system"), dict):
        primary = dict(raw["calendar_system"])
        primary.setdefault("is_default", True)
        alts = raw.get("calendar_alternatives") or []
        if not isinstance(alts, list):
            alts = []
        out["calendar_systems"] = [primary] + [
            dict(a) for a in alts if isinstance(a, dict)
        ]
    else:
        out["calendar_systems"] = list(_GENERIC_FALLBACK_PACK["calendar_systems"])

    # School types.
    school_types = raw.get("school_types")
    if isinstance(school_types, list) and school_types:
        out["school_types"] = list(school_types)
    else:
        out["school_types"] = list(_GENERIC_FALLBACK_PACK["school_types"])

    # Education levels.
    edu = raw.get("education_levels")
    if isinstance(edu, list) and edu:
        out["education_levels"] = list(edu)
    else:
        out["education_levels"] = list(_GENERIC_FALLBACK_PACK["education_levels"])

    # Terminology.
    term = raw.get("terminology")
    if isinstance(term, dict) and term:
        merged = dict(_GENERIC_FALLBACK_PACK["terminology"])
        merged.update(term)
        out["terminology"] = merged
    else:
        out["terminology"] = dict(_GENERIC_FALLBACK_PACK["terminology"])

    return out


def get_calendar_systems(country_code: str | None) -> list[dict[str, Any]]:
    """Just the calendar list for a country (1-3 options usually)."""
    return list(resolve_country_pack(country_code)["calendar_systems"])


def get_school_types(country_code: str | None) -> list[dict[str, Any]]:
    """Just the school-type cards list for a country (4-6 options usually)."""
    return list(resolve_country_pack(country_code)["school_types"])


def get_education_levels(country_code: str | None) -> list[dict[str, Any]]:
    """Just the granular education-level list (e.g. Year 1, Grade 6, ...)."""
    return list(resolve_country_pack(country_code)["education_levels"])


def get_terminology(country_code: str | None) -> dict[str, str]:
    """Just the terminology dict (teacher / principal / term / etc.)."""
    return dict(resolve_country_pack(country_code)["terminology"])


def get_default_calendar_code(country_code: str | None) -> str:
    """Return the default calendar `code` for this country (or "" if none)."""
    for cal in get_calendar_systems(country_code):
        if cal.get("is_default"):
            return str(cal.get("code") or "")
    cals = get_calendar_systems(country_code)
    return str(cals[0].get("code") or "") if cals else ""


def validate_school_type(country_code: str | None, school_type_code: str | None) -> str:
    """Return the school_type code if valid for the country, else "".

    Used in signup POST handlers to reject card values that aren't in the
    country's pack (e.g. someone posting school_type=preschool when the
    country pack only offers ["nursery","primary","secondary","university"]).
    """
    candidate = (school_type_code or "").strip().lower()
    if not candidate:
        return ""
    for st in get_school_types(country_code):
        if str(st.get("code") or "").strip().lower() == candidate:
            return candidate
    return ""


def validate_calendar_code(country_code: str | None, calendar_code: str | None) -> str:
    """Return the calendar code if valid for the country, else "".

    Sister of validate_school_type — defends POST handlers against arbitrary
    `term_preset` values.
    """
    candidate = (calendar_code or "").strip()
    if not candidate:
        return ""
    for cal in get_calendar_systems(country_code):
        if str(cal.get("code") or "").strip() == candidate:
            return candidate
    return ""


def resolve_primary_sector_for_school_type(
    country_code: str | None, school_type_code: str | None
) -> str:
    """Return the School.primary_sector value for a (country, school_type) pair.

    Empty string when nothing maps — caller should fall through to existing
    legacy `_SCHOOL_TYPE_TO_PRIMARY_SECTOR` mapping (kept for backwards
    compatibility with the v3.61.8 hardcoded form).
    """
    candidate = (school_type_code or "").strip().lower()
    if not candidate:
        return ""
    for st in get_school_types(country_code):
        if str(st.get("code") or "").strip().lower() == candidate:
            return str(st.get("primary_sector") or "").strip()
    return ""


def clear_cache() -> None:
    """Test helper — drop the lru_cache so changed seed data takes effect."""
    resolve_country_pack.cache_clear()


# ---------------------------------------------------------------------------
# Wave 2 (v3.62.5) — request-level resolution.
#
# `resolve_for_request(request)` is the canonical "what is THIS user's country?"
# helper used by the context processor + everywhere that needs to know the
# effective country for the current request (signup form, dashboards, date
# pickers, currency display).
#
# Resolution order:
#   1. request.school.country_code           — multi-tenant tenant context
#   2. request.session["onboarding_country_code"] — public signup flow
#   3. request.COOKIES["rmc_country"]        — long-lived UX preference
#   4. Accept-Language header tail           — best-effort browser hint
#   5. ""                                    — fall through to generic pack
# ---------------------------------------------------------------------------

def _country_from_school(request) -> str:
    school = getattr(request, "school", None)
    if school is None:
        return ""
    return normalize_country_code(getattr(school, "country_code", "") or "")


def _country_from_session(request) -> str:
    sess = getattr(request, "session", None)
    if sess is None:
        return ""
    try:
        return normalize_country_code(sess.get("onboarding_country_code") or "")
    except Exception:  # noqa: BLE001 — session backends can raise
        return ""


def _country_from_cookie(request) -> str:
    try:
        return normalize_country_code(request.COOKIES.get("rmc_country") or "")
    except Exception:  # noqa: BLE001
        return ""


def _country_from_accept_language(request) -> str:
    """Tail-of-primary-langtag heuristic, e.g. en-NG -> NG."""
    try:
        header = (request.META.get("HTTP_ACCEPT_LANGUAGE") or "").strip()
        if not header:
            return ""
        primary = header.split(",")[0].strip()
        if "-" not in primary:
            return ""
        return normalize_country_code(primary.split("-")[-1])
    except Exception:  # noqa: BLE001
        return ""


def resolve_country_for_request(request) -> str:
    """Return the effective ISO 3166-1 alpha-2 country code for this request."""
    for resolver in (
        _country_from_school,
        _country_from_session,
        _country_from_cookie,
        _country_from_accept_language,
    ):
        cc = resolver(request)
        if cc:
            return cc
    return ""


def resolve_for_request(request) -> dict:
    """Return the full localization pack for the current request.

    Same pack shape as ``resolve_country_pack`` but the country_code is
    derived from request context. Used by the context processor.
    """
    cc = resolve_country_for_request(request)
    pack = dict(resolve_country_pack(cc))
    pack["country_code"] = cc
    return pack
