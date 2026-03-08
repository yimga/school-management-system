from __future__ import annotations

from dataclasses import dataclass

import pytz

from apps.siteconfig.global_catalog import GlobalGeoCatalog

from .models import (
    CountryRegistry,
    EducationLevelRegistry,
    EducationSystemTypeRegistry,
    SubdivisionRegistry,
    DocumentTypeRegistry,
    FeeCategoryRegistry,
    GradeScaleRegistry,
    InstitutionTypeRegistry,
    AcademicTerminologyRegistry,
    LocaleRegistry,
    CalendarSystemRegistry,
)
from .currency_seed import ensure_currency_registry_seed


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


def ensure_document_type_seed() -> None:
    """Idempotent seed for document types (admissions/compliance)."""
    defaults = [
        {"code": "BIRTH_CERTIFICATE", "name": "Birth Certificate", "category": "identity", "sort_order": 10},
        {"code": "NATIONAL_ID", "name": "National ID", "category": "identity", "sort_order": 20},
        {"code": "PASSPORT", "name": "Passport", "category": "identity", "sort_order": 30},
        {"code": "VACCINATION_CARD", "name": "Vaccination Card", "category": "health", "sort_order": 40},
        {"code": "PREVIOUS_REPORT_CARD", "name": "Previous Report Card", "category": "academic", "sort_order": 50},
        {"code": "TRANSFER_CERTIFICATE", "name": "Transfer Certificate", "category": "academic", "sort_order": 60},
        {"code": "PROOF_OF_ADDRESS", "name": "Proof of Address", "category": "identity", "sort_order": 70},
        {"code": "GUARDIAN_CONSENT", "name": "Guardian Consent Form", "category": "compliance", "sort_order": 80},
        {"code": "VISA_RESIDENCY", "name": "Visa / Residency", "category": "identity", "sort_order": 90},
    ]
    for row in defaults:
        DocumentTypeRegistry.objects.update_or_create(
            code=row["code"],
            defaults={
                "name": row["name"],
                "category": row.get("category", ""),
                "sort_order": row.get("sort_order", 0),
                "is_active": True,
            },
        )


def ensure_fee_category_seed() -> None:
    """Idempotent seed for fee categories."""
    defaults = [
        {"code": "TUITION", "name": "Tuition", "sort_order": 10},
        {"code": "APPLICATION_FEE", "name": "Application Fee", "sort_order": 20},
        {"code": "TRANSPORT", "name": "Transport", "sort_order": 30},
        {"code": "LAB_FEE", "name": "Lab Fee", "sort_order": 40},
        {"code": "HOSTEL_FEE", "name": "Hostel Fee", "sort_order": 50},
        {"code": "EXAMINATION_FEE", "name": "Examination Fee", "sort_order": 60},
        {"code": "LIBRARY_FEE", "name": "Library Fee", "sort_order": 70},
        {"code": "GRADUATION_FEE", "name": "Graduation Fee", "sort_order": 80},
    ]
    for row in defaults:
        FeeCategoryRegistry.objects.update_or_create(
            code=row["code"],
            defaults={"name": row["name"], "sort_order": row.get("sort_order", 0), "is_active": True},
        )


def ensure_grade_scale_seed() -> None:
    """Idempotent seed for grade scale families."""
    defaults = [
        {"code": "0-20", "name": "0-20 scale", "family": "numeric", "sort_order": 10, "range_definition": {"min": 0, "max": 20}},
        {"code": "0-100", "name": "0-100 percentage", "family": "numeric", "sort_order": 20, "range_definition": {"min": 0, "max": 100}},
        {"code": "GPA_4", "name": "4.0 GPA", "family": "gpa", "sort_order": 30, "range_definition": {"min": 0, "max": 4}},
        {"code": "LETTER", "name": "Letter grades", "family": "letter", "sort_order": 40},
        {"code": "PASS_FAIL", "name": "Pass/Fail", "family": "binary", "sort_order": 50},
    ]
    for row in defaults:
        GradeScaleRegistry.objects.update_or_create(
            code=row["code"],
            defaults={
                "name": row["name"],
                "family": row.get("family", ""),
                "range_definition": row.get("range_definition", {}),
                "sort_order": row.get("sort_order", 0),
                "is_active": True,
            },
        )


def ensure_registry_baseline() -> None:
    ensure_country_registry_seed()
    ensure_currency_registry_seed()  # Part F 16.1: 195 currencies
    ensure_taxonomy_seed()
    sync_subdivisions_from_legacy_provinces()
    ensure_document_type_seed()
    ensure_fee_category_seed()
    ensure_grade_scale_seed()


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


def get_education_levels_for_country(country_code: str | None) -> list[dict]:
    """Education levels for onboarding; optional filter by country (country_labels)."""
    qs = EducationLevelRegistry.objects.filter(is_active=True).order_by("sort_order", "global_name")
    return [
        {
            "code": row.code,
            "global_name": row.global_name,
            "local_label": (row.country_labels or {}).get((country_code or "").upper(), row.global_name),
            "country_labels": row.country_labels or {},
        }
        for row in qs[:80]
    ]


def get_education_system_types_for_country(country_code: str | None) -> list[dict]:
    """Education system types for onboarding."""
    qs = EducationSystemTypeRegistry.objects.filter(is_active=True).order_by("sort_order", "name")
    return [
        {
            "code": row.code,
            "name": row.name,
            "category": row.category,
            "local_label": (row.country_labels or {}).get((country_code or "").upper(), row.name),
        }
        for row in qs[:50]
    ]


def get_institution_types_for_country(country_code: str | None) -> list[dict]:
    """Institution types for onboarding."""
    qs = InstitutionTypeRegistry.objects.filter(is_active=True).order_by("sort_order", "name")
    return [
        {
            "code": row.code,
            "name": row.name,
            "local_label": (row.country_labels or {}).get((country_code or "").upper(), row.name),
        }
        for row in qs[:40]
    ]


def get_document_types(country_code: str | None = None) -> list[dict]:
    """Document types for admissions/compliance (optional country filter)."""
    qs = DocumentTypeRegistry.objects.filter(is_active=True).order_by("sort_order", "name")
    if country_code:
        qs = qs.filter(country_code__in=[(country_code or "").upper()[:2], ""])
    return [{"code": row.code, "name": row.name, "category": row.category} for row in qs[:60]]


def get_fee_categories(country_code: str | None = None) -> list[dict]:
    """Fee categories for finance (optional country filter)."""
    qs = FeeCategoryRegistry.objects.filter(is_active=True).order_by("sort_order", "name")
    if country_code:
        qs = qs.filter(country_code__in=[(country_code or "").upper()[:2], ""])
    return [{"code": row.code, "name": row.name, "category": row.category} for row in qs[:60]]


def get_grade_scale_families(country_code: str | None = None) -> list[dict]:
    """Grade scale families for gradebook (optional country filter)."""
    qs = GradeScaleRegistry.objects.filter(is_active=True).order_by("sort_order", "name")
    if country_code:
        qs = qs.filter(country_code__in=[(country_code or "").upper()[:2], ""])
    return [
        {"code": row.code, "name": row.name, "family": row.family, "range_definition": row.range_definition or {}}
        for row in qs[:40]
    ]


def get_locales_for_country(country_code: str | None = None) -> list[dict]:
    """Locales for tenant setup."""
    qs = LocaleRegistry.objects.filter(is_active=True).order_by("sort_order", "name")
    return [{"code": row.code, "name": row.name, "is_rtl": row.is_rtl} for row in qs[:50]]


def get_calendar_systems_for_country(country_code: str | None = None) -> list[dict]:
    """Calendar systems for onboarding."""
    qs = CalendarSystemRegistry.objects.filter(is_active=True).order_by("sort_order", "name")
    if country_code:
        qs = qs.filter(country_code__in=[(country_code or "").upper()[:2], ""])
    return [{"code": row.code, "name": row.name, "term_count_per_year": row.term_count_per_year} for row in qs[:30]]


def get_terminology_packs_for_country(country_code: str | None = None) -> list[dict]:
    """Terminology packs for tenant setup."""
    qs = AcademicTerminologyRegistry.objects.filter(is_active=True).order_by("sort_order", "name")
    if country_code:
        qs = qs.filter(country_code__in=[(country_code or "").upper()[:2], ""])
    return [{"code": row.code, "name": row.name, "terminology": row.terminology or {}} for row in qs[:30]]
