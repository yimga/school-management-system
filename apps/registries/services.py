from __future__ import annotations

from dataclasses import dataclass

import pytz

from apps.siteconfig.global_catalog import GlobalGeoCatalog

from .models import (
    CountryRegistry,
    EducationLevelRegistry,
    EducationSystemTypeRegistry,
    SubdivisionRegistry,
)


DEFAULT_EDUCATION_LEVELS = (
    {
        "code": "PRIMARY",
        "global_name": "Primary",
        "description": "Foundational school years before lower secondary.",
        "sort_order": 10,
        "country_labels": {"US": "Elementary", "GB": "Primary"},
    },
    {
        "code": "SECONDARY",
        "global_name": "Secondary",
        "description": "Lower and upper secondary education.",
        "sort_order": 20,
        "country_labels": {"US": "High School"},
    },
    {
        "code": "TERTIARY",
        "global_name": "Tertiary",
        "description": "University, college, and post-secondary education.",
        "sort_order": 30,
        "country_labels": {"US": "Higher Education"},
    },
)


DEFAULT_EDUCATION_SYSTEM_TYPES = (
    {"code": "GENERAL", "name": "General", "category": "mainstream", "sort_order": 10},
    {"code": "TECHNICAL", "name": "Technical", "category": "career", "sort_order": 20},
    {"code": "STEM", "name": "STEM", "category": "specialist", "sort_order": 30},
    {"code": "TRADE", "name": "Trade", "category": "career", "sort_order": 40},
    {"code": "FAITH_BASED", "name": "Faith-based", "category": "governance", "sort_order": 50},
    {"code": "IB", "name": "IB", "category": "curriculum", "sort_order": 60},
    {"code": "CAMBRIDGE", "name": "Cambridge", "category": "curriculum", "sort_order": 70},
    {"code": "HYBRID", "name": "Hybrid", "category": "delivery", "sort_order": 80},
    {"code": "MONTESSORI", "name": "Montessori", "category": "pedagogy", "sort_order": 90},
    {"code": "ONLINE", "name": "Online", "category": "delivery", "sort_order": 100},
)


@dataclass(frozen=True)
class CountryChoice:
    code: str
    alpha3_code: str
    name: str
    timezone: str


def ensure_country_registry_seed() -> int:
    existing = CountryRegistry.objects.count()
    if existing >= 190:
        return existing

    created = 0
    for alpha2, name in sorted(pytz.country_names.items(), key=lambda item: item[1]):
        alpha2 = str(alpha2 or "").upper()
        if not alpha2:
            continue
        alpha3 = GlobalGeoCatalog.normalize_country_code(alpha2)
        if len(alpha3) != 3:
            alpha3 = ""
        timezones = pytz.country_timezones.get(alpha2) or []
        defaults = GlobalGeoCatalog.country_defaults(alpha3 or alpha2)
        _, was_created = CountryRegistry.objects.update_or_create(
            code=alpha2,
            defaults={
                "alpha3_code": alpha3,
                "name": str(name or alpha2),
                "default_language": defaults.get("default_language") or "en",
                "default_currency": defaults.get("currency") or "USD",
                "default_timezone": (timezones[0] if timezones else defaults.get("timezone")) or "UTC",
            },
        )
        if was_created:
            created += 1
    return CountryRegistry.objects.count()


def ensure_taxonomy_seed() -> None:
    for row in DEFAULT_EDUCATION_LEVELS:
        EducationLevelRegistry.objects.update_or_create(
            code=row["code"],
            defaults={
                "global_name": row["global_name"],
                "description": row["description"],
                "sort_order": row["sort_order"],
                "country_labels": row.get("country_labels") or {},
                "is_active": True,
            },
        )
    for row in DEFAULT_EDUCATION_SYSTEM_TYPES:
        EducationSystemTypeRegistry.objects.update_or_create(
            code=row["code"],
            defaults={
                "name": row["name"],
                "description": row.get("description", ""),
                "category": row.get("category", ""),
                "sort_order": row.get("sort_order", 0),
                "country_labels": row.get("country_labels") or {},
                "is_active": True,
            },
        )


def sync_subdivisions_from_legacy_provinces() -> int:
    from apps.siteconfig.models import Province

    created = 0
    for province in Province.objects.select_related("region").all():
        alpha2 = GlobalGeoCatalog.alpha2_for_country(province.region_id)
        if not alpha2:
            continue
        country = CountryRegistry.objects.filter(code=alpha2).first()
        if not country:
            continue
        _, was_created = SubdivisionRegistry.objects.update_or_create(
            country=country,
            code=str(province.code or province.name).upper()[:32],
            defaults={
                "name": province.name,
                "subdivision_type": "province",
                "metadata": {
                    "legacy_province_id": province.pk,
                    "legacy_region_code": province.region_id,
                },
            },
        )
        if was_created:
            created += 1
    return created


def ensure_registry_baseline() -> None:
    ensure_country_registry_seed()
    ensure_taxonomy_seed()
    sync_subdivisions_from_legacy_provinces()


def list_country_choices() -> list[dict[str, str]]:
    ensure_country_registry_seed()
    rows = CountryRegistry.objects.filter(is_active=True).order_by("name")
    return [
        {
            "code": row.code,
            "code_alpha2": row.code,
            "code_alpha3": row.alpha3_code or "",
            "name": row.name,
            "timezone": row.default_timezone or "UTC",
        }
        for row in rows
    ]


def list_subdivision_choices(country_code: str | None) -> list[dict[str, str]]:
    raw = (country_code or "").strip().upper()
    alpha2 = raw if len(raw) == 2 else GlobalGeoCatalog.alpha2_for_country(raw)
    if not alpha2:
        return []
    rows = (
        SubdivisionRegistry.objects.select_related("country")
        .filter(country_id=alpha2, is_active=True)
        .order_by("name")
    )
    return [
        {
            "id": row.id,
            "code": row.code,
            "name": row.name,
            "type": row.subdivision_type,
            "country_code": row.country_id,
        }
        for row in rows
    ]
