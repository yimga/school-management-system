"""Idempotent, non-destructive bootstrap reconciliation for existing tenants.

Tenant creation has several entry points (public signup, operator provisioning,
imports, tests, and legacy migrations).  The newer entry points capture rich
localization and education intent, while older rows can legitimately predate
those fields.  This module closes that historical gap without overwriting an
operator's explicit choices:

* explicit scalar, M2M, settings, and plan values always win;
* only missing values receive registry-backed recommendations;
* recommendations are deterministic and recorded in ``School.settings``;
* platform-owned education profiles and the default plan are bound through
  their canonical resolvers rather than duplicated here.

It is safe to run on every deployment and before every tenant seed fan-out.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from django.db import transaction


_SCHOOL_TYPE_MODALITY = {
    "BASE_SCHOOL": "GENERAL",
    "TECHNICAL_COLLEGE": "TECHNICAL",
    "STEM_ACADEMY": "STEM",
}

_SCHOOL_TYPE_LEVELS = {
    "BASE_SCHOOL": ("PRIMARY", "SECONDARY"),
    "TECHNICAL_COLLEGE": ("SECONDARY", "TERTIARY"),
    "STEM_ACADEMY": ("PRIMARY", "SECONDARY"),
}


@dataclass(frozen=True)
class TenantSeedReconciliation:
    school_slug: str
    changed_fields: tuple[str, ...]
    education_system_types: tuple[str, ...]
    education_levels: tuple[str, ...]
    education_profile_code: str
    plan_slug: str

    @property
    def changed(self) -> bool:
        return bool(self.changed_fields)


def _merge_missing(target: dict[str, Any], defaults: dict[str, Any]) -> bool:
    """Recursively add absent/blank values while preserving all user values."""
    changed = False
    for key, default in defaults.items():
        current = target.get(key)
        if isinstance(default, dict):
            if not isinstance(current, dict):
                if current not in (None, ""):
                    continue
                target[key] = {}
                current = target[key]
                changed = True
            changed = _merge_missing(current, default) or changed
            continue
        if key not in target:
            target[key] = default
            changed = True
        elif current in (None, "") and default not in (None, ""):
            target[key] = default
            changed = True
    return changed


def _recommended_sector(school) -> str:
    existing = str(getattr(school, "primary_sector", "") or "").strip().upper()
    if existing:
        return existing
    country = str(getattr(school, "country_code", "") or "").strip().upper()
    school_type = str(getattr(school, "school_type", "") or "").strip()
    try:
        from apps.siteconfig.country_localization_service import (
            resolve_primary_sector_for_school_type,
        )

        resolved = resolve_primary_sector_for_school_type(country, school_type)
    except (ImportError, AttributeError, TypeError, ValueError):
        resolved = ""
    if resolved:
        return resolved.strip().upper()
    sub_system = str(getattr(school, "sub_system", "") or "").strip().upper()
    return "INTERNATIONAL" if sub_system == "INT" else "PRIVATE"


@transaction.atomic
def reconcile_tenant_seed_baseline(school) -> TenantSeedReconciliation:
    """Fill only missing, safely inferable tenant bootstrap values."""
    from apps.registries.models import (
        EducationLevelRegistry,
        EducationSystemTypeRegistry,
    )
    from apps.schools.plan_resolution import ensure_school_plan
    from apps.schools.school_settings_seed import (
        build_initial_school_settings,
        resolve_school_geo_create_fields,
    )
    from apps.siteconfig.education_profile_engine import (
        ensure_region_for_country,
        resolve_profile_for_school,
    )

    changed: list[str] = []
    update_fields: list[str] = []
    country = str(getattr(school, "country_code", "") or "").strip().upper()
    region = getattr(school, "default_region", None)

    if region is None and country:
        region = ensure_region_for_country(country)
        if region is not None:
            school.default_region = region
            update_fields.append("default_region")
            changed.append("default_region")

    if not country and region is not None:
        from apps.siteconfig.global_catalog import GlobalGeoCatalog

        country = (
            GlobalGeoCatalog.alpha2_for_country(str(region.code or "")) or ""
        ).upper()
        if country:
            school.country_code = country
            update_fields.append("country_code")
            changed.append("country_code")

    geo = resolve_school_geo_create_fields(country)
    for field, value in (
        ("timezone", geo.get("timezone")),
        ("currency", geo.get("currency")),
        ("default_language", geo.get("default_language")),
        ("compliance_region", geo.get("compliance_region")),
    ):
        if hasattr(school, field) and not str(getattr(school, field, "") or "").strip() and value:
            setattr(school, field, value)
            update_fields.append(field)
            changed.append(field)

    if hasattr(school, "primary_language") and not str(
        getattr(school, "primary_language", "") or ""
    ).strip():
        language = str(getattr(school, "default_language", "") or "").strip()
        if language:
            school.primary_language = language[:16]
            update_fields.append("primary_language")
            changed.append("primary_language")

    sector = _recommended_sector(school)
    if not str(getattr(school, "primary_sector", "") or "").strip() and sector:
        school.primary_sector = sector
        update_fields.append("primary_sector")
        changed.append("primary_sector")

    settings_payload = dict(getattr(school, "settings", None) or {})
    school_type = str(getattr(school, "school_type", "") or "").strip().upper()
    recommended_level_codes = _SCHOOL_TYPE_LEVELS.get(
        school_type, _SCHOOL_TYPE_LEVELS["BASE_SCHOOL"]
    )
    initial_settings = build_initial_school_settings(
        country_code=country,
        school_type_code=school_type,
        language_code=str(getattr(school, "primary_language", "") or ""),
        education_cycles=list(recommended_level_codes),
        seed_marker="_seeded_at_platform_reconciliation",
    )
    if _merge_missing(settings_payload, initial_settings):
        school.settings = settings_payload
        update_fields.append("settings")
        changed.append("settings.localization")

    if update_fields:
        school.save(update_fields=list(dict.fromkeys([*update_fields, "updated_at"])))

    if not school.education_system_types.exists():
        codes = [sector, _SCHOOL_TYPE_MODALITY.get(school_type, "GENERAL")]
        rows = list(
            EducationSystemTypeRegistry.objects.filter(
                code__in={code for code in codes if code}, is_active=True
            )
        )
        if rows:
            school.education_system_types.set(rows)
            changed.append("education_system_types")

    if not school.education_levels.exists():
        rows = list(
            EducationLevelRegistry.objects.filter(
                code__in=recommended_level_codes, is_active=True
            )
        )
        if rows:
            school.education_levels.set(rows)
            changed.append("education_levels")

    profile = resolve_profile_for_school(school, auto_create=True)
    profile_code = str(getattr(profile, "code", "") or "")
    if profile_code:
        settings_payload = dict(getattr(school, "settings", None) or {})
        if not str(settings_payload.get("education_profile_code") or "").strip():
            settings_payload["education_profile_code"] = profile_code
            provisioning = settings_payload.get("provisioning")
            if not isinstance(provisioning, dict):
                provisioning = {}
                settings_payload["provisioning"] = provisioning
            provisioning["education_profile_mode"] = "auto"
            school.settings = settings_payload
            school.save(update_fields=["settings", "updated_at"])
            changed.append("education_profile_code")

    if ensure_school_plan(school):
        changed.append("plan")

    return TenantSeedReconciliation(
        school_slug=str(school.slug),
        changed_fields=tuple(dict.fromkeys(changed)),
        education_system_types=tuple(
            school.education_system_types.order_by("code").values_list("code", flat=True)
        ),
        education_levels=tuple(
            school.education_levels.order_by("code").values_list("code", flat=True)
        ),
        education_profile_code=profile_code,
        plan_slug=str(getattr(getattr(school, "plan", None), "slug", "") or ""),
    )


__all__ = ["TenantSeedReconciliation", "reconcile_tenant_seed_baseline"]
