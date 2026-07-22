"""Canonical initial School.settings + geo create fields for all create paths.

Closes PGL-009 divergence: public signup, CLI ``create_school``, operator
``api_create_school``, and other entry points share localization / governance /
country-pack defaults instead of each inventing a thinner settings blob.
"""

from __future__ import annotations

from typing import Any


def build_initial_localization_settings(
    *,
    country_code: str = "",
    school_type_code: str = "",
    language_code: str = "",
    language_codes: list[str] | None = None,
    education_cycles: list[str] | None = None,
    calendar_code: str = "",
    seed_marker: str = "_seeded_at_signup",
) -> dict[str, Any]:
    """Signup-shaped ``settings["localization"]`` block."""
    from apps.siteconfig.country_localization_service import get_default_calendar_code

    cc = (country_code or "").strip().upper()[:2]
    lang = (language_code or "").strip()
    langs = list(language_codes or ([lang] if lang else []))
    cycles = list(education_cycles or [])
    cal = (calendar_code or "").strip() or (
        get_default_calendar_code(cc) if cc else ""
    )
    block: dict[str, Any] = {
        "country_code": cc,
        "calendar_code": cal,
        "school_type_code": (school_type_code or "").strip(),
        "education_cycles": cycles,
        "language_code": lang,
        "primary_language_code": lang,
        "language_codes": langs,
        seed_marker: True,
    }
    return block


def build_initial_governance_settings(country_code: str) -> dict[str, Any] | None:
    cc = (country_code or "").strip().upper()[:2]
    if not cc:
        return None
    from apps.governance.country_matrix_service import signup_governance_defaults

    gov = dict(signup_governance_defaults(cc) or {})
    gov["_seeded_at_signup"] = True
    return gov


def build_initial_school_settings(
    *,
    country_code: str = "",
    school_type_code: str = "",
    language_code: str = "",
    language_codes: list[str] | None = None,
    education_cycles: list[str] | None = None,
    calendar_code: str = "",
    seed_marker: str = "_seeded_at_signup",
    include_governance: bool = True,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Full initial ``School.settings`` dict (localization + optional governance)."""
    settings: dict[str, Any] = {}
    if (
        country_code
        or school_type_code
        or language_code
        or language_codes
        or education_cycles
        or calendar_code
    ):
        settings["localization"] = build_initial_localization_settings(
            country_code=country_code,
            school_type_code=school_type_code,
            language_code=language_code,
            language_codes=language_codes,
            education_cycles=education_cycles,
            calendar_code=calendar_code,
            seed_marker=seed_marker,
        )
    if include_governance and country_code:
        gov = build_initial_governance_settings(country_code)
        if gov:
            settings["governance"] = gov
    if extra:
        settings.update(extra)
    return settings


def resolve_school_geo_create_fields(
    country_code: str,
    *,
    language_code: str = "",
) -> dict[str, Any]:
    """Model-column defaults from the country pack (timezone/currency/language/regime)."""
    from django.conf import settings as dj_settings

    from apps.schools.compliance_region import derive_compliance_region

    cc = (country_code or "").strip().upper()[:2]
    country_defaults: dict[str, Any] = {}
    try:
        from apps.schools.signup_views import GlobalGeoCatalog

        country_defaults = dict(GlobalGeoCatalog.country_defaults(cc) or {})
    except (ImportError, AttributeError, TypeError, ValueError):
        country_defaults = {}

    lang = (language_code or "").strip() or str(
        country_defaults.get("default_language") or ""
    )
    return {
        "timezone": str(
            country_defaults.get("timezone")
            or getattr(dj_settings, "DEFAULT_SCHOOL_TIMEZONE", "UTC")
        ),
        "currency": str(country_defaults.get("currency") or "")[:3],
        "default_language": lang[:16],
        "compliance_region": derive_compliance_region(cc),
    }
