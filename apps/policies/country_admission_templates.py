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
so a country always has a sensible admission format the admin merely tweaks. The
country→format mapping follows regional administrative convention rather than
being hand-listed per country: Anglophone / Commonwealth (Africa, South Asia,
Gulf, Caribbean) use the slash form ``GBHS/26/0001``; Francophone / Lusophone /
Hispanophone (Africa, continental Europe, Latin America) use the dash form
``LYC-26-0001``; the UK, Nordics and East Asia use the compact ``26GBHS0001``; and
the US/Canada/Philippines use the bare sequence ``260001``.

Applied SAFELY, per-tenant, at provisioning time (never in the global resolver):
a school's own ``TenantAdmissionNumberPolicy`` is seeded from here only when it
has none AND has issued no admission numbers yet — so an existing tenant's format
is never changed under it. Callers pass either ``School.country_code`` (usually
ISO alpha-2) or ``RegionConfig.code`` (ISO alpha-3); both are normalized here.
"""

from __future__ import annotations

# Common formats (placeholders are rendered by identifier_policy_service).
_SLASH = "{school_code}/{year_2digit}/{seq_4digit}"   # GBHS/26/0001 — Anglophone / Commonwealth
_DASH = "{school_code}-{year_2digit}-{seq_4digit}"    # LYC-26-0001 — Francophone / Lusophone / Hispanophone
_COMPACT = "{year_2digit}{school_code}{seq_4digit}"   # 26GBHS0001 — UK / Nordic / East Asia
_SEQ_YEAR = "{year_2digit}{seq_4digit}"               # 260001 — US-style

# The universal default when a country has no curated template.
GENERIC_ADMISSION_TEMPLATE = _COMPACT

# ISO alpha-2 country groups by admission-format convention. Cameroon is bilingual
# but its Anglophone GCE tradition uses the slash form, so it sits with SLASH.
_SLASH_COUNTRIES = {
    # Anglophone & Commonwealth Africa
    "CM", "NG", "GH", "KE", "UG", "TZ", "ZA", "RW", "MW", "ZW", "ZM", "BW",
    "NA", "LS", "SZ", "MU", "SC", "GM", "SL", "LR", "SS",
    # South Asia (Commonwealth)
    "IN", "PK", "BD", "LK",
    # Commonwealth / British-influenced Asia-Pacific & Caribbean
    "SG", "MY", "HK", "IE", "JM", "TT", "BB", "FJ", "PG",
    # Gulf / MENA (Arabic-region schools commonly use the slash form)
    "AE", "QA", "SA", "KW", "BH", "OM", "JO",
}
_DASH_COUNTRIES = {
    # Francophone West / Central Africa
    "FR", "CI", "SN", "ML", "BF", "NE", "GN", "TG", "BJ", "MR", "GA", "CG",
    "CD", "TD", "CF", "GQ", "BI", "DJ", "KM", "MG",
    # Lusophone Africa
    "AO", "MZ", "ST", "GW", "CV",
    # Continental Europe (Romance + Germanic that use dashed roll numbers)
    "DE", "ES", "PT", "IT", "BE", "NL",
    # Latin America (Hispanophone / Lusophone)
    "MX", "BR", "AR", "CL", "PE", "CO",
    # Turkey (Franco-influenced administrative forms)
    "TR",
}
_COMPACT_COUNTRIES = {
    # United Kingdom + Nordic / Central-Eastern Europe
    "GB", "SE", "NO", "DK", "FI", "CH", "PL", "AT", "GR", "RO", "UA", "RU",
    # East / South-East Asia (numeric student-number traditions)
    "JP", "KR", "CN", "ID", "TH", "VN", "NP",
    # North Africa / Levant (compact numeric)
    "EG", "MA", "DZ", "TN", "LY", "IL", "IR", "IQ", "SY", "YE",
}
_SEQ_YEAR_COUNTRIES = {"US", "CA", "PH"}

# Full-coverage extension so EVERY sovereign country resolves a regional template
# (not merely the generic fallback), grouped by the same conventions.
_SLASH_COUNTRIES |= {
    # English-speaking Caribbean / Commonwealth
    "GY", "BZ", "AG", "BS", "DM", "GD", "KN", "LC", "VC",
    # Commonwealth Asia-Pacific
    "BN", "MV", "KI", "NR", "SB", "TO", "TV", "WS", "VU",
    # Arabic-region
    "PS",
}
_DASH_COUNTRIES |= {
    # Latin America (Hispanophone / Lusophone)
    "VE", "EC", "BO", "PY", "UY", "CR", "NI", "HN", "GT", "SV", "PA", "DO", "CU",
    "SR", "HT", "TL",
    # European Romance / micro-states
    "AD", "MC", "LU", "SM", "VA",
}
_COMPACT_COUNTRIES |= {
    # Central & Eastern Europe / Nordic / Caucasus
    "AL", "AM", "AZ", "BA", "BG", "BY", "CY", "CZ", "EE", "GE", "HR", "HU",
    "LT", "LV", "MD", "ME", "MK", "PL", "RS", "SI", "SK", "IS", "LI", "MT", "EH",
    # Central Asia
    "KZ", "KG", "TJ", "TM", "UZ",
    # East / South-East Asia
    "TW", "MO", "MM", "KH", "LA", "MN", "KP", "BT",
    # Afghanistan
    "AF",
}
_SEQ_YEAR_COUNTRIES |= {
    # US-affiliated Pacific
    "FM", "MH", "PW",
}


def _build_templates() -> dict[str, str]:
    table: dict[str, str] = {}
    for iso in _SLASH_COUNTRIES:
        table[iso] = _SLASH
    for iso in _DASH_COUNTRIES:
        table[iso] = _DASH
    for iso in _COMPACT_COUNTRIES:
        table[iso] = _COMPACT
    for iso in _SEQ_YEAR_COUNTRIES:
        table[iso] = _SEQ_YEAR
    return table


# ISO alpha-2 → format template.
_ADMISSION_TEMPLATES: dict[str, str] = _build_templates()


def _normalize_key(code: str) -> str:
    """ISO code → alpha-2 lookup key. Accepts alpha-2 (pass-through) or alpha-3
    (converted via ``pycountry`` when available, else a best-effort two-letter
    prefix — admission format is a cosmetic, admin-editable default, so a rare
    mis-map is harmless). Empty in → empty out."""
    key = (code or "").strip().upper()
    if not key:
        return ""
    if len(key) == 2:
        return key
    if len(key) == 3:
        try:
            import pycountry

            match = pycountry.countries.get(alpha_3=key)
            if match and getattr(match, "alpha_2", None):
                return str(match.alpha_2).upper()
        except Exception:  # noqa: BLE001 — missing lib / unknown code
            pass
        return key[:2]
    return key[:2]


def template_for_country(code: str) -> str:
    """Return the curated admission template for an ISO code (alpha-2 or alpha-3),
    or the generic fallback. Never raises."""
    key = _normalize_key(code)
    if not key:
        return GENERIC_ADMISSION_TEMPLATE
    return _ADMISSION_TEMPLATES.get(key) or GENERIC_ADMISSION_TEMPLATE


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
