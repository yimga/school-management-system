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

  1. Tenant DB override (Wave 8) — operator-edited rows in
     ``apps.registries.models.CountryRegistry`` win over seed when the row
     carries a non-empty ``cockpit_override_payload`` (dict-shaped).
  2. Exact entry in ``_seed_country_localization.COUNTRY_LOCALIZATION``
     (hand-researched Tier 1 data — Nigeria, France, India, ...)
  3. Regional default keyed by ``COUNTRY_REGIONAL_DEFAULT[code]``
     (e.g. "BJ" -> "africa-francophone" -> use the francophone-Africa default pack)
  4. Hard-coded ``_GENERIC_FALLBACK_PACK`` below
     (covers totally unknown / blank / malformed country codes)

The seed module is imported lazily so the service is testable + boots even
when the seed file is missing (returns _GENERIC_FALLBACK_PACK universally).

## Per-language education systems (Wave 6, v3.62.8 — 2026-05-22)

Multilingual countries can carry per-language education-system overlays
under ``pack["languages"]``:

    {
        "languages": [
            {
                "code": "en", "native_name": "English", "is_official": True,
                "is_default": False,
                "region": "Anglophone Northwest + Southwest",
                "education_system": {
                    "system_name": "English Subsystem (GCE O/A Level)",
                    "school_types": [...],
                    "education_levels": [...],
                    "terminology": {...},
                    "calendar_system": {...},
                },
            },
            {"code": "fr", "native_name": "Français", "is_default": True, ...},
        ],
        # baseline (used when language not selected, or country monolingual)
        "school_types": [...], "education_levels": [...], ...,
    }

Helpers ``get_languages(cc)``, ``resolve_language_pack(cc, lang)`` overlay
the per-language education system on the country baseline. A country
without ``languages`` falls through to its baseline pack unchanged
(monolingual contract). The signup form's language picker calls these
helpers to re-render cards when the user switches language.

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
def _resolve_country_pack_seed_only(country_code: str | None) -> dict[str, Any]:
    """Seed + regional + fallback resolution; never touches the DB.

    Split out so the DB-override hot path (resolve_country_pack) can compose
    the in-memory result with a per-tenant DB row without paying the seed
    parse cost on every call.
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


def resolve_country_pack(country_code: str | None) -> dict[str, Any]:
    """Return the full localization pack for `country_code`.

    Always returns a complete pack with keys: calendar_systems, school_types,
    education_levels, terminology, _source. Never raises.

    Composition order (Wave 8 v3.62.8):
      1. Seed/regional/fallback (in-memory, cached).
      2. If `CountryRegistry[cc].cockpit_override_payload` is a non-empty
         dict, shallow-merge over the seed result (lists overridden wholesale,
         dicts merged one level deep). DB miss / blank override / import
         failure all fall back silently to seed-only.

    `_source` carries which lookup matched, useful for logging and tests:
      - "country:NG"    — Tier 1 exact match
      - "regional:africa-anglophone" — regional default for country NG
      - "generic-fallback" — fell all the way through
      - "+db-override" suffix when a DB override layered on top
    """
    base = _resolve_country_pack_seed_only(country_code)
    cc = normalize_country_code(country_code)
    if not cc:
        return dict(base)

    override = _load_db_override(cc)
    if not override:
        out = dict(base)
        if cc == "IN":
            _apply_india_calendar_alternatives(out)
        return out

    merged = _shallow_merge_pack(dict(base), override)
    merged["_source"] = str(base.get("_source") or "unknown") + "+db-override"
    # Wave 13: when IN is the country, surface all 3 state-board calendar
    # variants on the picker so an operator picking ANY language can override
    # the default to match their actual state's academic year. Applied here
    # so /api/v1/localization/IN/ (no lang) also shows them.
    if cc == "IN":
        _apply_india_calendar_alternatives(merged)
    return merged


def _shallow_merge_pack(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Shallow-merge `override` onto `base`.

    Top-level lists in override REPLACE the base list wholesale (so an operator
    who wants to add one extra school_type re-submits the whole list — same
    contract as Django form re-post). Top-level dicts merge one level deep
    (terminology.teacher can be overridden without losing terminology.principal).
    Scalars override directly. Unknown keys land at top level.
    """
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            merged = dict(base[k])
            merged.update(v)
            base[k] = merged
        else:
            base[k] = v
    return base


@lru_cache(maxsize=512)
def _load_db_override(cc: str) -> dict[str, Any]:
    """Pull operator-edited override JSON from CountryRegistry for `cc`.

    Returns {} when (a) the registry app or column is missing, (b) no row for
    this country, (c) the override JSON is not a dict, or (d) ANY exception
    fires. Never raises — the seed path is always safe to fall back to.

    Cached aggressively (lru_cache) because the override is per-country, not
    per-tenant — operators editing this surface trigger a `clear_cache()`.
    """
    try:
        from django.apps import apps as django_apps
        try:
            CountryRegistry = django_apps.get_model("registries", "CountryRegistry")
        except LookupError:
            return {}
        if not hasattr(CountryRegistry, "_meta"):
            return {}
        # tenant-isolation-allow: country-registry-public-reference-shared-across-all-tenants
        row = CountryRegistry.objects.filter(code=cc).only("cockpit_override_payload").first()
        if row is None:
            return {}
        payload = getattr(row, "cockpit_override_payload", None) or {}
        if not isinstance(payload, dict):
            return {}
        return payload
    except Exception:  # noqa: BLE001 — DB read must never break signup
        return {}


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

    # Wave 6: per-language overlay list. Preserved verbatim so the picker
    # can render education-system-divergent options (CM Anglophone/Franco,
    # CA EN/FR, BE NL/FR/DE, CH DE/FR/IT/RM, IN/PK/LK/SG/MY/PH/ZA/...).
    langs = raw.get("languages")
    if isinstance(langs, list) and langs:
        out["languages"] = [dict(l) for l in langs if isinstance(l, dict)]

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
    """Test helper / operator hook — drop caches so edits take effect.

    Operator admin form for CountryRegistry calls this in post_save so the
    new override layer becomes visible without a process restart.
    """
    _resolve_country_pack_seed_only.cache_clear()
    _load_db_override.cache_clear()


# ---------------------------------------------------------------------------
# Wave 6 (v3.62.8 2026-05-22) — per-language education systems.
#
# Multilingual countries (CM/CA/BE/CH/IN/ZA/SG/MY/LK/PH/PK and others)
# carry pack["languages"] -- a list of dicts with optional per-language
# "education_system" overlay that REPLACES the country baseline's
# school_types / education_levels / terminology / calendar_systems.
#
# The signup-form language picker calls `resolve_language_pack(cc, lang)`
# which returns the merged pack so re-rendering cards is a single API call.
# ---------------------------------------------------------------------------

def get_languages(country_code: str | None) -> list[dict[str, Any]]:
    """Return the country's official languages, or [] when monolingual.

    Each entry shape (Wave 6 schema):
        {"code": "fr", "native_name": "Français", "is_official": True,
         "is_default": True, "region": "Francophone (8 regions)",
         "education_system": {...} OR not-present (uses country baseline)}
    """
    pack = resolve_country_pack(country_code)
    languages = pack.get("languages") or []
    if not isinstance(languages, list):
        return []
    out: list[dict[str, Any]] = []
    for item in languages:
        if isinstance(item, dict) and (item.get("code") or "").strip():
            out.append(dict(item))
    return out


def get_default_language(country_code: str | None) -> str:
    """Return the default language code for the country (or "" when none)."""
    for lang in get_languages(country_code):
        if lang.get("is_default"):
            return str(lang.get("code") or "").strip().lower()
    langs = get_languages(country_code)
    return str(langs[0].get("code") or "").strip().lower() if langs else ""


def validate_language_code(country_code: str | None, language_code: str | None) -> str:
    """Return language_code if valid for the country, else "".

    Used in signup POST handlers to reject arbitrary language values.
    Falls open when country has no `languages` overlay (monolingual contract).
    """
    candidate = (language_code or "").strip().lower()
    if not candidate:
        return ""
    langs = get_languages(country_code)
    if not langs:
        return ""
    for lang in langs:
        if str(lang.get("code") or "").strip().lower() == candidate:
            return candidate
    return ""


# Wave 13 (v3.62.17 — 2026-05-23) — per-state India calendar variance.
# India's 11 state-board systems cluster into 3 distinct academic-year start
# months: June (KN/ML/MR/OR), January (BN/AS), April (PA/UR/HI most belt
# states). When an operator picks a language, the primary calendar is the
# language's state-aligned one — but the picker shows ALL 3 variants so a
# Hindi-medium school in Bihar (January calendar) can pick the right one
# without giving up Hindi medium of instruction.
_INDIA_STATE_BOARD_CALENDAR_VARIANTS: list[dict[str, Any]] = [
    {
        "code": "in-state-jun",
        "label": "3 Terms (June-April)",
        "sub": "Karnataka / Kerala / Maharashtra / Odisha / Tamil Nadu / Telangana / Gujarat",
        "term_count": 3,
        "academic_year_starts_month": 6,
        "term_names": ["1st Term", "2nd Term", "3rd Term"],
    },
    {
        "code": "in-state-apr",
        "label": "3 Terms (April-March)",
        "sub": "Hindi belt / Punjab / Urdu-medium / CBSE/ICSE national calendar",
        "term_count": 3,
        "academic_year_starts_month": 4,
        "term_names": ["1st Term", "2nd Term", "3rd Term"],
    },
    {
        "code": "in-state-jan",
        "label": "3 Terms (January-December)",
        "sub": "Bengal / Assam (SEBA) / Tripura",
        "term_count": 3,
        "academic_year_starts_month": 1,
        "term_names": ["1st Term", "2nd Term", "3rd Term"],
    },
]


def _apply_india_calendar_alternatives(merged: dict[str, Any]) -> None:
    """If we're in India, expose ALL 3 state-board calendar variants in the
    picker — with the language's own variant marked as default — so an
    operator can keep their language and still pick a non-default
    state-board calendar (e.g. Hindi medium with Bengal's January start).

    Mutates ``merged`` in place. No-op when the country pack doesn't have
    `_source` referencing 'IN' or the calendar list is already multi-entry.
    """
    cur = merged.get("calendar_systems") or []
    if not isinstance(cur, list) or len(cur) != 1:
        return
    primary = cur[0]
    if not isinstance(primary, dict):
        return
    primary_month = int(primary.get("academic_year_starts_month") or 0)
    # Re-attach the other 2 variants as non-default options. Keep the
    # language's own calendar as the default (preserved primary).
    variants = []
    for v in _INDIA_STATE_BOARD_CALENDAR_VARIANTS:
        if int(v.get("academic_year_starts_month") or 0) == primary_month:
            continue  # already the default
        v_copy = dict(v)
        v_copy["is_default"] = False
        variants.append(v_copy)
    if variants:
        primary_copy = dict(primary)
        primary_copy.setdefault("is_default", True)
        merged["calendar_systems"] = [primary_copy] + variants


def resolve_language_pack(
    country_code: str | None, language_code: str | None
) -> dict[str, Any]:
    """Return the country pack with the per-language education-system overlay.

    When `language_code` is empty OR the country has no `languages` overlay
    OR the language has no `education_system` block, returns the baseline
    country pack unchanged (monolingual contract).

    Mutually-exclusive overlay keys: ``school_types``, ``education_levels``,
    ``terminology``, ``calendar_systems`` -- if present in the language
    pack's `education_system`, they REPLACE the country baseline. Other
    keys (e.g. ``writing_direction``, ``name_order``) stay at country level.
    """
    base = dict(resolve_country_pack(country_code))
    cc = normalize_country_code(country_code)
    if not cc:
        return base
    valid = validate_language_code(cc, language_code)
    if not valid:
        return base
    for lang in get_languages(cc):
        if str(lang.get("code") or "").strip().lower() != valid:
            continue
        edu = lang.get("education_system") or {}
        if not isinstance(edu, dict) or not edu:
            return base
        # Build merged pack: country baseline overridden by per-language fields.
        merged = dict(base)
        merged["language_code"] = valid
        merged["language_native_name"] = str(lang.get("native_name") or "")
        merged["language_region"] = str(lang.get("region") or "")
        if isinstance(edu.get("school_types"), list) and edu["school_types"]:
            merged["school_types"] = list(edu["school_types"])
        if isinstance(edu.get("education_levels"), list) and edu["education_levels"]:
            merged["education_levels"] = list(edu["education_levels"])
        if isinstance(edu.get("terminology"), dict) and edu["terminology"]:
            term = dict(_GENERIC_FALLBACK_PACK["terminology"])
            term.update(base.get("terminology") or {})
            term.update(edu["terminology"])
            merged["terminology"] = term
        cal_systems = edu.get("calendar_systems")
        if isinstance(cal_systems, list) and cal_systems:
            merged["calendar_systems"] = list(cal_systems)
        elif isinstance(edu.get("calendar_system"), dict):
            primary = dict(edu["calendar_system"])
            primary.setdefault("is_default", True)
            merged["calendar_systems"] = [primary]
        merged["system_name"] = str(edu.get("system_name") or "").strip()
        merged["_source"] = (
            f"{base.get('_source', 'unknown')}+language:{valid}"
        )
        # Wave 13: India per-state calendar variance picker.
        if cc == "IN":
            _apply_india_calendar_alternatives(merged)
        return merged
    return base


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


def _country_from_geoip(request) -> str:
    """Wave 10 (v3.62.10) — opt-in IP-based country lookup.

    Lazy-imports the GeoIP service so this module boots even when the
    geoip_country_lookup module is missing or geoip2 isn't installed.
    Returns "" unless an operator has set RMC_GEOIP_BACKEND to a non-noop
    value. Never raises.
    """
    try:
        from .geoip_country_lookup import lookup_country
        return normalize_country_code(lookup_country(request))
    except Exception:  # noqa: BLE001
        return ""


def resolve_country_for_request(request) -> str:
    """Return the effective ISO 3166-1 alpha-2 country code for this request.

    Wave 10 (v3.62.10) order:
      1. request.school.country_code            — multi-tenant context
      2. request.session["onboarding_country_code"] — public signup flow
      3. request.COOKIES["rmc_country"]         — long-lived UX preference
      4. GeoIP backend                          — opt-in (Cloudflare /
                                                   X-Country-Code / MaxMind)
      5. Accept-Language header tail            — fallback browser hint
      6. ""                                     — falls through to generic
    """
    for resolver in (
        _country_from_school,
        _country_from_session,
        _country_from_cookie,
        _country_from_geoip,         # Wave 10
        _country_from_accept_language,
    ):
        cc = resolver(request)
        if cc:
            return cc
    return ""


def resolve_for_request(request) -> dict:
    """Return the full localization pack for the current request.

    Same pack shape as ``resolve_country_pack`` but the country_code AND
    language_code are derived from request context, and per-language
    education system is layered on when applicable. Used by the context
    processor.
    """
    cc = resolve_country_for_request(request)
    lang = resolve_language_for_request(request, cc)
    pack = dict(resolve_language_pack(cc, lang) if lang else resolve_country_pack(cc))
    pack["country_code"] = cc
    pack["language_code"] = pack.get("language_code") or lang or ""
    return pack


# ---------------------------------------------------------------------------
# Wave 6 — request-level language resolution.
#
# Resolution order (matches country resolver pattern):
#   1. request.school.primary_language     — tenant-set value (after Wave 6)
#   2. request.session["onboarding_language"] — public signup flow
#   3. request.COOKIES["rmc_language"]        — long-lived UX preference
#   4. Accept-Language header head           — browser hint
#   5. country default language              — pack's `is_default`
#   6. ""                                    — monolingual fallback (no overlay)
# ---------------------------------------------------------------------------

def _language_from_school(request) -> str:
    school = getattr(request, "school", None)
    if school is None:
        return ""
    return (getattr(school, "primary_language", "") or "").strip().lower()


def _language_from_session(request) -> str:
    sess = getattr(request, "session", None)
    if sess is None:
        return ""
    try:
        return (sess.get("onboarding_language") or "").strip().lower()
    except Exception:  # noqa: BLE001
        return ""


def _language_from_cookie(request) -> str:
    try:
        return (request.COOKIES.get("rmc_language") or "").strip().lower()
    except Exception:  # noqa: BLE001
        return ""


def _language_from_accept_language(request) -> str:
    """Head-of-primary-langtag heuristic, e.g. fr-CA -> fr."""
    try:
        header = (request.META.get("HTTP_ACCEPT_LANGUAGE") or "").strip()
        if not header:
            return ""
        primary = header.split(",")[0].strip()
        if "-" in primary:
            primary = primary.split("-")[0]
        return primary.strip().lower()[:8]
    except Exception:  # noqa: BLE001
        return ""


def resolve_language_for_request(request, country_code: str | None = None) -> str:
    """Return the effective language code for this request, validated against
    the country's `languages` overlay.

    Falls through to the country's default language. Returns "" when the
    country is monolingual (no overlay) — caller should NOT apply a language
    overlay in that case.
    """
    cc = (country_code or resolve_country_for_request(request) or "").upper()
    if not cc:
        return ""
    candidates = (
        _language_from_school(request),
        _language_from_session(request),
        _language_from_cookie(request),
        _language_from_accept_language(request),
    )
    for cand in candidates:
        v = validate_language_code(cc, cand)
        if v:
            return v
    return get_default_language(cc)
