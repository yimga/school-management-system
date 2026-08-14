"""Country-default admission-number templates — the country_defaults layer.

The effective-policy cascade advertises ``platform_defaults ⊕ country_defaults ⊕
tenant_overrides``, but the country admission layer shipped EMPTY: no country
carried a default admission-number format, and ``RegionConfig.student_id_format``
(the intended per-region hook) was a blank field nothing ever seeded. So every
fresh tenant fell back to the generic ``{yy}{school_code}{seq}{spec}{class}``
format regardless of local convention.

This module supplies a curated per-country default template (using the same
placeholders the generator understands: ``{year_2digit}``, ``{school_code}``,
``{seq_4digit}``, ``{spec_code}``, ``{class_segment}``) plus a generic fallback,
so a country always has a sensible admission format the admin merely tweaks.

Applied SAFELY, per-tenant, at provisioning time (never in the global resolver):
a school's own ``TenantAdmissionNumberPolicy`` is seeded from here only when it
has none AND has issued no admission numbers yet — so an existing tenant's format
is never changed under it. Keyed by ISO country (alpha-2 and alpha-3 both, since
callers pass either ``School.country_code`` or ``RegionConfig.code``).
"""

from __future__ import annotations

# Common formats (placeholders are rendered by identifier_policy_service).
_SLASH = "{school_code}/{year_2digit}/{seq_4digit}"   # GBHS/26/0001 — Anglophone Africa
_DASH = "{school_code}-{year_2digit}-{seq_4digit}"    # LYC-26-0001 — Francophone
_COMPACT = "{year_2digit}{school_code}{seq_4digit}"   # 26GBHS0001
_SEQ_YEAR = "{year_2digit}{seq_4digit}"               # 260001 — US-style

_ADMISSION_TEMPLATES: dict[str, str] = {
    "CM": _SLASH, "CMR": _SLASH,
    "NG": _SLASH, "NGA": _SLASH,
    "GH": _SLASH, "GHA": _SLASH,
    "KE": _SLASH, "KEN": _SLASH,
    "UG": _SLASH, "UGA": _SLASH,
    "TZ": _SLASH, "TZA": _SLASH,
    "IN": _SLASH, "IND": _SLASH,
    "ZA": _SLASH, "ZAF": _SLASH,
    "GB": _COMPACT, "GBR": _COMPACT,
    "FR": _DASH, "FRA": _DASH,
    "DE": _DASH, "DEU": _DASH,
    "US": _SEQ_YEAR, "USA": _SEQ_YEAR,
    "CA": _SEQ_YEAR, "CAN": _SEQ_YEAR,
}

# The universal default when a country has no curated template.
GENERIC_ADMISSION_TEMPLATE = _COMPACT


def template_for_country(code: str) -> str:
    """Return the curated admission template for an ISO code (alpha-2 or alpha-3),
    or the generic fallback. Never raises."""
    key = (code or "").strip().upper()
    if not key:
        return GENERIC_ADMISSION_TEMPLATE
    return _ADMISSION_TEMPLATES.get(key) or _ADMISSION_TEMPLATES.get(key[:2]) or GENERIC_ADMISSION_TEMPLATE


def resolve_admission_template(school) -> str:
    """Return the admission-number template for a school.

    Cascade: the school's ``RegionConfig.student_id_format`` (region-editable
    override, revived by the data migration) → the curated per-country table →
    the generic fallback. Always returns a usable template."""
    region = getattr(school, "default_region", None)
    if region is not None:
        region_fmt = (getattr(region, "student_id_format", "") or "").strip()
        if region_fmt:
            return region_fmt
    iso = (getattr(school, "country_code", None) or "").strip()
    if not iso and region is not None:
        iso = (getattr(region, "code", "") or "").strip()
    return template_for_country(iso)
