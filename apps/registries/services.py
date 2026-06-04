from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import pytz
from django.db import models

from apps.siteconfig.global_catalog import GlobalGeoCatalog

from .models import (
    CountryRegistry,
    CurrencyRegistry,
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
    # Curriculum / delivery / pedagogy (pre-wedge)
    {"code": "GENERAL", "name": "General", "category": "mainstream", "sort_order": 10},
    {"code": "TECHNICAL", "name": "Technical", "category": "career", "sort_order": 20},
    {"code": "STEM", "name": "STEM", "category": "specialist", "sort_order": 30},
    {"code": "TRADE", "name": "Trade", "category": "career", "sort_order": 40},
    {"code": "IB", "name": "IB", "category": "curriculum", "sort_order": 60},
    {
        "code": "CAMBRIDGE",
        "name": "Cambridge",
        "category": "curriculum",
        "sort_order": 70,
    },
    {"code": "HYBRID", "name": "Hybrid", "category": "delivery", "sort_order": 80},
    {
        "code": "MONTESSORI",
        "name": "Montessori",
        "category": "pedagogy",
        "sort_order": 90,
    },
    {"code": "ONLINE", "name": "Online", "category": "delivery", "sort_order": 100},
    # SOT Wedges 14–22: Education systems (sector) — non-negotiable; seed all nine.
    {
        "code": "PUBLIC",
        "name": "Public / state",
        "category": "sector",
        "sort_order": 140,  # magic-number-allow: display-sort-order-value
        "description": "Funding and compliance; district/ministry reporting; statutory returns; role model (state, district, school).",
    },
    {
        "code": "PRIVATE",
        "name": "Private / independent",
        "category": "sector",
        "sort_order": 150,  # magic-number-allow: display-sort-order-value
        "description": "Tuition, fees, aid; admissions; same platform as public.",
    },
    {
        "code": "CHARTER",
        "name": "Charter",
        "category": "sector",
        "sort_order": 160,  # magic-number-allow: display-sort-order-value
        "description": "Hybrid public accountability and school autonomy; reporting and funding rules.",
    },
    {
        "code": "INTERNATIONAL",
        "name": "International",
        "category": "sector",
        "sort_order": 170,  # magic-number-allow: display-sort-order-value
        "description": "Multi-country, multi-curriculum (IB, UK, US, national); one school, many systems; language and currency.",
    },
    {
        "code": "FAITH_BASED",
        "name": "Faith-based",
        "category": "sector",
        "sort_order": 180,  # magic-number-allow: display-sort-order-value
        "description": "Same as private plus optional faith-specific reporting or branding.",
    },
    {
        "code": "HOME_SCHOOL",
        "name": "Home-school / hybrid",
        "category": "sector",
        "sort_order": 190,  # magic-number-allow: display-sort-order-value
        "description": "Part-time, external, or home-school students; attendance and assessment flexibility.",
    },
    {
        "code": "GOVERNMENT_MINISTRY",
        "name": "Government / ministry",
        "category": "sector",
        "sort_order": 200,
        "description": "Ministry or regional authority as tenant or aggregator; district control plane; national reporting.",
    },
    {
        "code": "NGO",
        "name": "NGO / non-profit",
        "category": "sector",
        "sort_order": 210,  # magic-number-allow: display-sort-order-value
        "description": "Donor and program reporting; grants; often private + advancement.",
    },
    {
        "code": "MULTI_CAMPUS",
        "name": "Multi-campus / group",
        "category": "sector",
        "sort_order": 220,  # magic-number-allow: display-sort-order-value
        "description": "One tenant or hierarchy (group → campuses); shared reporting and governance.",
    },
)

# SOT §0.2.1: Wedge 14–22 education system sector codes (single source for validation and UI).
WEDGE_14_22_SECTOR_CODES = (
    "PUBLIC",
    "PRIVATE",
    "CHARTER",
    "INTERNATIONAL",
    "FAITH_BASED",
    "HOME_SCHOOL",
    "GOVERNMENT_MINISTRY",
    "NGO",
    "MULTI_CAMPUS",
)


@dataclass(frozen=True)
class CountryChoice:
    code: str
    alpha3_code: str
    name: str
    timezone: str


def ensure_country_registry_seed() -> int:
    existing = CountryRegistry.objects.count()
    if existing >= 190:  # magic-number-allow: display-sort-order-floor
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
                "default_timezone": (
                    timezones[0] if timezones else defaults.get("timezone")
                )
                or "UTC",
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
    from apps.global_registries.models import Province

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


_ISO3166_SUBDIVISION_TYPE_ALIASES: dict[str, str] = {
    "state": "state",
    "province": "province",
    "region": "region",
    "district": "district",
    "territory": "territory",
    "department": "department",
    "county": "county",
    "municipality": "municipality",
    "canton": "canton",
    "parish": "parish",
    "prefecture": "prefecture",
    "governorate": "governorate",
    "oblast": "oblast",
    "raion": "raion",
    "commune": "commune",
    "borough": "borough",
    "city": "city",
    "capital": "capital",
    "country": "country",
}


def map_pycountry_subdivision_type(type_name: str | None) -> str:
    """Normalize pycountry subdivision ``type`` labels to registry slug values."""
    raw = (type_name or "subdivision").strip().lower()
    slug = re.sub(r"[^a-z0-9]+", "_", raw).strip("_") or "subdivision"
    return _ISO3166_SUBDIVISION_TYPE_ALIASES.get(slug, slug)[:40]


def subdivision_code_from_iso3166(iso_code: str, country_alpha2: str) -> str:
    """Return the subdivision suffix from an ISO 3166-2 code (e.g. US-CA -> CA)."""
    code = (iso_code or "").strip().upper()
    prefix = f"{country_alpha2.strip().upper()}-"
    if code.startswith(prefix):
        code = code[len(prefix) :]
    return code[:32]


@dataclass(frozen=True)
class Iso3166SubdivisionSeedResult:
    countries_processed: int
    subdivisions_created: int
    subdivisions_updated: int
    countries_with_subdivisions: tuple[str, ...]


def _sovereign_country_codes_from_matrix() -> frozenset[str]:
    repo_root = Path(__file__).resolve().parents[2]
    matrix_path = repo_root / "docs" / "generated" / "country_governance_matrix.json"
    if not matrix_path.is_file():
        return frozenset()
    try:
        matrix = json.loads(matrix_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return frozenset()
    return frozenset(
        str(row.get("iso_alpha2") or "").upper()
        for row in matrix.get("rows") or []
        if row.get("sovereign_state")
    )


def seed_iso3166_subdivisions(
    *,
    dry_run: bool = False,
    country_codes: list[str] | None = None,
) -> Iso3166SubdivisionSeedResult:
    """Bulk-seed SubdivisionRegistry rows from pycountry ISO 3166-2 subdivisions."""
    import pycountry

    ensure_country_registry_seed()

    qs = CountryRegistry.objects.all()
    if country_codes:
        codes = {str(code or "").strip().upper() for code in country_codes if str(code or "").strip()}
        qs = qs.filter(code__in=codes)
    elif not qs.exists():
        for alpha2, name in sorted(pytz.country_names.items(), key=lambda item: item[1]):
            alpha2 = str(alpha2 or "").upper()
            if not alpha2:
                continue
            CountryRegistry.objects.get_or_create(
                code=alpha2,
                defaults={"name": str(name or alpha2)},
            )
        qs = CountryRegistry.objects.all()

    sovereign_codes = _sovereign_country_codes_from_matrix()
    created = 0
    updated = 0
    countries_with: set[str] = set()

    for country in qs.order_by("code"):
        alpha2 = str(country.code or "").upper()
        if not alpha2:
            continue
        subdivisions = list(pycountry.subdivisions.get(country_code=alpha2))
        if not subdivisions and alpha2 in sovereign_codes:
            subdivisions = []

        if not subdivisions:
            if alpha2 in sovereign_codes:
                if dry_run:
                    countries_with.add(alpha2)
                    continue
                _, was_created = SubdivisionRegistry.objects.update_or_create(
                    country=country,
                    code="NAT",
                    defaults={
                        "name": country.name,
                        "subdivision_type": "country",
                        "metadata": {
                            "source": "national_fallback",
                            "iso3166_2": False,
                        },
                        "is_active": True,
                    },
                )
                if was_created:
                    created += 1
                else:
                    updated += 1
                countries_with.add(alpha2)
            continue

        for subdivision in subdivisions:
            sub_code = subdivision_code_from_iso3166(
                str(getattr(subdivision, "code", "") or ""),
                alpha2,
            )
            if not sub_code:
                continue
            defaults = {
                "name": str(getattr(subdivision, "name", "") or sub_code),
                "subdivision_type": map_pycountry_subdivision_type(
                    getattr(subdivision, "type", None)
                ),
                "metadata": {
                    "source": "iso3166_2",
                    "iso3166_2": True,
                    "pycountry_code": str(getattr(subdivision, "code", "") or ""),
                    "pycountry_type": str(getattr(subdivision, "type", "") or ""),
                },
                "is_active": True,
            }
            if dry_run:
                countries_with.add(alpha2)
                continue
            _, was_created = SubdivisionRegistry.objects.update_or_create(
                country=country,
                code=sub_code,
                defaults=defaults,
            )
            if was_created:
                created += 1
            else:
                updated += 1
            countries_with.add(alpha2)

    return Iso3166SubdivisionSeedResult(
        countries_processed=qs.count(),
        subdivisions_created=created,
        subdivisions_updated=updated,
        countries_with_subdivisions=tuple(sorted(countries_with)),
    )


def update_governance_matrix_subdivision_flags(
    *,
    matrix_path: Path | None = None,
    write_shards: bool = True,
) -> int:
    """Set ``deep_layers.subdivisions_seeded`` for countries with registry rows."""
    repo_root = Path(__file__).resolve().parents[2]
    path = matrix_path or (repo_root / "docs" / "generated" / "country_governance_matrix.json")
    if not path.is_file():
        return 0

    subdivision_counts = dict(
        SubdivisionRegistry.objects.values("country_id")
        .annotate(total=models.Count("id"))
        .values_list("country_id", "total")
    )

    matrix = json.loads(path.read_text(encoding="utf-8"))
    flagged = 0
    for row in matrix.get("rows") or []:
        iso = str(row.get("iso_alpha2") or "").upper()
        if not iso:
            continue
        deep = row.setdefault("deep_layers", {})
        has_rows = subdivision_counts.get(iso, 0) >= 1
        if has_rows:
            deep["subdivisions_seeded"] = True
            flagged += 1
        else:
            deep["subdivisions_seeded"] = False

    matrix["generated_at"] = datetime.now(timezone.utc).isoformat()
    path.write_text(
        json.dumps(matrix, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    if write_shards:
        shard_dir = path.parent / "country_governance_matrix"
        shard_dir.mkdir(parents=True, exist_ok=True)
        for row in matrix.get("rows") or []:
            iso = str(row.get("iso_alpha2") or "")
            if not iso:
                continue
            shard_path = shard_dir / f"{iso}.json"
            shard_path.write_text(
                json.dumps(row, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )

    return flagged


def ensure_document_type_seed() -> None:
    """Idempotent seed for document types (admissions/compliance)."""
    defaults = [
        {
            "code": "BIRTH_CERTIFICATE",
            "name": "Birth Certificate",
            "category": "identity",
            "sort_order": 10,
        },
        {
            "code": "NATIONAL_ID",
            "name": "National ID",
            "category": "identity",
            "sort_order": 20,
        },
        {
            "code": "PASSPORT",
            "name": "Passport",
            "category": "identity",
            "sort_order": 30,
        },
        {
            "code": "VACCINATION_CARD",
            "name": "Vaccination Card",
            "category": "health",
            "sort_order": 40,
        },
        {
            "code": "PREVIOUS_REPORT_CARD",
            "name": "Previous Report Card",
            "category": "academic",
            "sort_order": 50,
        },
        {
            "code": "TRANSFER_CERTIFICATE",
            "name": "Transfer Certificate",
            "category": "academic",
            "sort_order": 60,
        },
        {
            "code": "PROOF_OF_ADDRESS",
            "name": "Proof of Address",
            "category": "identity",
            "sort_order": 70,
        },
        {
            "code": "GUARDIAN_CONSENT",
            "name": "Guardian Consent Form",
            "category": "compliance",
            "sort_order": 80,
        },
        {
            "code": "VISA_RESIDENCY",
            "name": "Visa / Residency",
            "category": "identity",
            "sort_order": 90,
        },
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
            defaults={
                "name": row["name"],
                "sort_order": row.get("sort_order", 0),
                "is_active": True,
            },
        )


def ensure_grade_scale_seed() -> None:
    """Idempotent seed for grade scale families."""
    defaults = [
        {
            "code": "0-20",
            "name": "0-20 scale",
            "family": "numeric",
            "sort_order": 10,
            "range_definition": {"min": 0, "max": 20},
        },
        {
            "code": "0-100",
            "name": "0-100 percentage",
            "family": "numeric",
            "sort_order": 20,
            "range_definition": {"min": 0, "max": 100},
        },
        {
            "code": "GPA_4",
            "name": "4.0 GPA",
            "family": "gpa",
            "sort_order": 30,
            "range_definition": {"min": 0, "max": 4},
        },
        {
            "code": "LETTER",
            "name": "Letter grades",
            "family": "letter",
            "sort_order": 40,
        },
        {
            "code": "PASS_FAIL",
            "name": "Pass/Fail",
            "family": "binary",
            "sort_order": 50,
        },
        {
            "code": "NUMERIC_1_5",
            "name": "1-5 scale (Post-Soviet)",
            "family": "numeric",
            "sort_order": 60,
            "range_definition": {"min": 1, "max": 5, "pass_threshold": 3},
            "metadata": {"ranking_mode": "average", "governance_archetype": "europe-eastern"},
        },
        {
            "code": "WAEC_LETTER",
            "name": "WAEC letter bands",
            "family": "letter",
            "sort_order": 70,
            "metadata": {
                "ranking_mode": "average",
                "boundary_map": [
                    {"grade": "A1", "min": 75, "max": 100},
                    {"grade": "B2", "min": 70, "max": 74.99},
                    {"grade": "C6", "min": 50, "max": 69.99},
                    {"grade": "F9", "min": 0, "max": 49.99},
                ],
            },
        },
        {
            "code": "STANDARD_SCORE_T",
            "name": "T-score (East Asia)",
            "family": "standard_score",
            "sort_order": 80,
            "range_definition": {"min": 0, "max": 100},
            "metadata": {"ranking_mode": "standard_score_t"},
        },
        {
            "code": "QUALITATIVE_PD",
            "name": "Qualitative descriptors",
            "family": "qualitative",
            "sort_order": 90,
            "metadata": {"ranking_mode": "average"},
        },
    ]
    for row in defaults:
        GradeScaleRegistry.objects.update_or_create(
            code=row["code"],
            defaults={
                "name": row["name"],
                "family": row.get("family", ""),
                "range_definition": row.get("range_definition", {}),
                "metadata": row.get("metadata", {}),
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


def list_currency_choices() -> list[dict[str, str | int]]:
    ensure_currency_registry_seed()
    rows = CurrencyRegistry.objects.filter(is_active=True).order_by(
        "sort_order", "name"
    )
    return [
        {
            "code": row.code,
            "name": row.name,
            "symbol": row.symbol or "",
            "decimal_places": int(row.decimal_places or 0),
        }
        for row in rows
    ]


def is_known_currency_code(currency_code: str | None) -> bool:
    code = (currency_code or "").strip().upper()
    if not code:
        return False
    ensure_currency_registry_seed()
    return CurrencyRegistry.objects.filter(code=code, is_active=True).exists()


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
    qs = EducationLevelRegistry.objects.filter(is_active=True).order_by(
        "sort_order", "global_name"
    )
    return [
        {
            "code": row.code,
            "global_name": row.global_name,
            "local_label": (row.country_labels or {}).get(
                (country_code or "").upper(), row.global_name
            ),
            "country_labels": row.country_labels or {},
        }
        for row in qs[:80]
    ]


def get_education_system_types_for_country(country_code: str | None) -> list[dict]:
    """Education system types for onboarding."""
    qs = EducationSystemTypeRegistry.objects.filter(is_active=True).order_by(
        "sort_order", "name"
    )
    return [
        {
            "code": row.code,
            "name": row.name,
            "category": row.category,
            "local_label": (row.country_labels or {}).get(
                (country_code or "").upper(), row.name
            ),
        }
        for row in qs[:50]
    ]


def list_sector_system_types_14_22() -> list[dict]:
    """SOT §0.2.1: All nine wedge 14–22 education system (sector) types for control-plane and Create School."""
    ensure_taxonomy_seed()
    qs = EducationSystemTypeRegistry.objects.filter(
        code__in=WEDGE_14_22_SECTOR_CODES,
        is_active=True,
    ).order_by("sort_order", "name")
    return [
        {
            "code": row.code,
            "name": row.name,
            "description": (row.description or "").strip(),
            "wedge": 14 + list(WEDGE_14_22_SECTOR_CODES).index(row.code)
            if row.code in WEDGE_14_22_SECTOR_CODES
            else None,
        }
        for row in qs
    ]


# Wedge 14–22: Suggested role/permission templates by sector (RBAC by system type).
# Use when assigning default roles or showing "suggested roles for your sector".
SECTOR_ROLE_SUGGESTIONS: dict[str, dict] = {
    "PUBLIC": {
        "suggested_roles": [
            "PRINCIPAL",
            "VICE_PRINCIPAL",
            "BURSAR",
            "CENSOR",
            "DEAN",
            "ACADEMICS_STAFF",
        ],
        "description": "Ministry reporting; statutory returns; state/district/school role model.",
    },
    "GOVERNMENT_MINISTRY": {
        "suggested_roles": [
            "ADMIN",  # role-string-allow: sector-suggested-role-code
            "PRINCIPAL",
            "BURSAR",
            "ACCOUNTANT",
            "SECRETARY",
            "IT_ADMIN",
        ],
        "description": "District control plane; national reporting; statutory.",
    },
    "PRIVATE": {
        "suggested_roles": [
            "PROPRIETOR",  # role-string-allow: sector-suggested-role-code
            "PRINCIPAL",
            "BURSAR",
            "ACCOUNTANT",
            "TEACHER",  # role-string-allow: sector-suggested-role-code
            "ADMIN",  # role-string-allow: sector-suggested-role-code
        ],
        "description": "Tuition, fees, aid; admissions.",
    },
    "NGO": {
        "suggested_roles": [
            "ADMIN",  # role-string-allow: sector-suggested-role-code
            "PRINCIPAL",
            "BURSAR",
            "ACCOUNTANT",
            "COMMS_STAFF",
            "SECRETARY",
        ],
        "description": "Donor/campaign reporting; advancement hub.",
    },
    "INTERNATIONAL": {
        "suggested_roles": [
            "ADMIN",  # role-string-allow: sector-suggested-role-code
            "PRINCIPAL",
            "DEAN",
            "HOD",
            "IT_ADMIN",
            "ACADEMICS_STAFF",
        ],
        "description": "Multi-curriculum; multi-language/currency.",
    },
    "MULTI_CAMPUS": {
        "suggested_roles": [
            "ADMIN",  # role-string-allow: sector-suggested-role-code
            "PRINCIPAL",
            "VICE_PRINCIPAL",
            "BURSAR",
            "DEAN",
            "IT_ADMIN",
        ],
        "description": "Hierarchy; shared reporting and governance.",
    },
    "CHARTER": {
        "suggested_roles": [
            "PRINCIPAL",
            "BURSAR",
            "DEAN",
            "ACADEMICS_STAFF",
            "ACCOUNTANT",
        ],
        "description": "Hybrid accountability; funding rules.",
    },
    "FAITH_BASED": {
        "suggested_roles": [
            "PROPRIETOR",  # role-string-allow: sector-suggested-role-code
            "PRINCIPAL",
            "BURSAR",
            "DEAN",
            "DISCIPLINE_MASTER",
        ],
        "description": "As private; optional faith reporting/branding.",
    },
    "HOME_SCHOOL": {
        "suggested_roles": ["ADMIN", "TEACHER", "PARENT", "ACADEMICS_STAFF"],  # role-string-allow: sector-suggested-role-code
        "description": "Flexible attendance/assessment.",
    },
}


def get_sector_role_suggestions(primary_sector: str | None) -> dict:
    """Return suggested role codes and description for a sector (Wedge 14–22 RBAC by system type)."""
    sector = (primary_sector or "").strip().upper()
    return SECTOR_ROLE_SUGGESTIONS.get(
        sector, {"suggested_roles": [], "description": ""}
    )


# Bootstrap contact user must not receive portal-only AccessRoles
_SECTOR_BOOTSTRAP_SKIP_ACCESS_ROLES = frozenset({"STUDENT", "PARENT", "EMPLOYER"})  # role-string-allow: bootstrap-skip-access-role-set


def apply_wedge_14_22_sector_access_roles_to_user(school, user) -> dict:
    """
    On school provisioning: attach AccessRole rows for sector suggested_roles to the bootstrap user.
    Ensures ADMIN AccessRole is included when present. Idempotent (M2M add).
    Skips STUDENT/PARENT/EMPLOYER for the ops contact account.
    """
    if school is None or user is None or not getattr(user, "pk", None):
        return {"applied": [], "skipped": "missing_user_or_school"}
    try:
        from apps.accounts.models import AccessRole
    except ImportError:
        return {"applied": [], "skipped": "accounts_import"}

    sector = (getattr(school, "primary_sector", None) or "").strip().upper()
    if sector not in WEDGE_14_22_SECTOR_CODES:
        try:
            for st in school.education_system_types.all()[:32]:
                c = (getattr(st, "code", None) or "").strip().upper()
                if c in WEDGE_14_22_SECTOR_CODES:
                    sector = c
                    break
        except (AttributeError, TypeError, ValueError):
            pass
    if not sector:
        return {"applied": [], "skipped": "no_primary_sector"}

    data = get_sector_role_suggestions(sector)
    codes = [str(c).strip().upper() for c in (data.get("suggested_roles") or []) if c]

    def _ensure_access_role(code: str) -> AccessRole:
        ar, _ = AccessRole.objects.get_or_create(
            code=code,
            defaults={
                "name": code.replace("_", " ").title(),
                "description": "",
            },
        )
        return ar

    applied: list[str] = []
    for code in codes:
        if code in _SECTOR_BOOTSTRAP_SKIP_ACCESS_ROLES:
            continue
        ar = _ensure_access_role(code)
        user.roles.add(ar)
        applied.append(code)
    admin_ar = _ensure_access_role("ADMIN")  # role-string-allow: bootstrap-admin-access-role-code
    user.roles.add(admin_ar)
    admin_attached = True
    return {
        "applied": applied,
        "admin_access_role_attached": admin_attached,
        "sector": sector,
        "description": (data.get("description") or "").strip(),
    }


def build_education_system_support_accordion(safe_reverse) -> list[dict]:
    """
    Full accordion data for all nine Wedge 14–22 sectors (Education systems page).
    safe_reverse: callable taking url name, returns str|None (e.g. super_views_wedge._safe_reverse).
    """
    from apps.registries.models import EducationSystemTypeRegistry

    def u(*names: str) -> str | None:
        for n in names:
            if not n:
                continue
            out = safe_reverse(n)
            if out:
                return out
        return None

    _out_reports = u("studio_os:output")
    report_library = (
        f"{_out_reports}?pane=reports"
        if _out_reports
        else u("reports:report_list")
    )

    def actions_for(sector: str) -> list[dict]:
        seen: set[str] = set()
        out: list[dict] = []

        def add(label: str, url: str | None) -> None:
            if url and url not in seen:
                seen.add(url)
                out.append({"label": label, "url": url})

        add("Setup Studio", u("siteconfig:guided_onboarding"))
        add("Create school", u("super:create_school_wizard"))
        add("Curriculum & region packs", u("super:curriculum_packs"))
        add("Blueprints catalog", u("super:blueprints_catalog"))
        add("Runtime inspector (RBAC/config)", u("super:runtime_inspector"))
        add("Registries", u("super:registries_overview"))
        if sector in ("PUBLIC", "GOVERNMENT_MINISTRY", "CHARTER"):
            add("Report library", report_library)
        if sector == "NGO":
            add("Advancement hub", u("super:advancement_hub"))
        if sector == "INTERNATIONAL":
            add("Geography (region packs)", u("super:geography"))
        if sector == "MULTI_CAMPUS":
            add("Group & campuses", u("super:group_campuses"))
            add("Schools list", u("super:schools_list"))
        if sector == "PRIVATE":
            add("Finance dashboard", u("finance:dashboard"))
            add("Fee / billing setup", u("super:blueprints_catalog"))
        if sector == "FAITH_BASED":
            add("Experience Studio (branding)", u("studio_os:experience"))
            add("Report library", report_library)
        if sector == "HOME_SCHOOL":
            add("Geography / locale", u("super:geography"))
            add("Academics (teacher hub)", u("academics:teacher_syllabus_hub"))
        if sector == "PUBLIC":
            add("Geography (statutory context)", u("super:geography"))
        if sector == "GOVERNMENT_MINISTRY":
            add("District / schools list", u("super:schools_list"))
        return out

    rows: list[dict] = []
    for code in WEDGE_14_22_SECTOR_CODES:
        reg = EducationSystemTypeRegistry.objects.filter(
            code=code, is_active=True
        ).first()
        name = reg.name if reg else code.replace("_", " ").title()
        sug = get_sector_role_suggestions(code)
        desc = (sug.get("description") or "").strip()
        reg_desc = (reg.description or "").strip() if reg else ""
        sr = ", ".join(sug.get("suggested_roles") or [])
        parts = [p for p in (desc, reg_desc) if p]
        message = " ".join(parts)
        if sr:
            message = f"{message} Suggested staff roles (also applied to bootstrap user on provision): {sr}."
        rows.append(
            {
                "code": code,
                "name": name,
                "message": message.strip() or "—",
                "next_actions": actions_for(code),
            }
        )
    return rows


def get_institution_types_for_country(country_code: str | None) -> list[dict]:
    """Institution types for onboarding."""
    qs = InstitutionTypeRegistry.objects.filter(is_active=True).order_by(
        "sort_order", "name"
    )
    return [
        {
            "code": row.code,
            "name": row.name,
            "local_label": (row.country_labels or {}).get(
                (country_code or "").upper(), row.name
            ),
        }
        for row in qs[:40]
    ]


def get_document_types(country_code: str | None = None) -> list[dict]:
    """Document types for admissions/compliance (optional country filter)."""
    qs = DocumentTypeRegistry.objects.filter(is_active=True).order_by(
        "sort_order", "name"
    )
    if country_code:
        qs = qs.filter(country_code__in=[(country_code or "").upper()[:2], ""])
    return [
        {"code": row.code, "name": row.name, "category": row.category}
        for row in qs[:60]
    ]


def get_fee_categories(country_code: str | None = None) -> list[dict]:
    """Fee categories for finance (optional country filter)."""
    qs = FeeCategoryRegistry.objects.filter(is_active=True).order_by(
        "sort_order", "name"
    )
    if country_code:
        qs = qs.filter(country_code__in=[(country_code or "").upper()[:2], ""])
    return [
        {"code": row.code, "name": row.name, "category": row.category}
        for row in qs[:60]
    ]


def get_grade_scale_families(country_code: str | None = None) -> list[dict]:
    """Grade scale families for gradebook (optional country filter)."""
    qs = GradeScaleRegistry.objects.filter(is_active=True).order_by(
        "sort_order", "name"
    )
    if country_code:
        qs = qs.filter(country_code__in=[(country_code or "").upper()[:2], ""])
    return [
        {
            "code": row.code,
            "name": row.name,
            "family": row.family,
            "range_definition": row.range_definition or {},
        }
        for row in qs[:40]
    ]


def get_locales_for_country(country_code: str | None = None) -> list[dict]:
    """Locales for tenant setup."""
    qs = LocaleRegistry.objects.filter(is_active=True).order_by("sort_order", "name")
    return [
        {"code": row.code, "name": row.name, "is_rtl": row.is_rtl} for row in qs[:50]
    ]


def get_calendar_systems_for_country(country_code: str | None = None) -> list[dict]:
    """Calendar systems for onboarding."""
    qs = CalendarSystemRegistry.objects.filter(is_active=True).order_by(
        "sort_order", "name"
    )
    if country_code:
        qs = qs.filter(country_code__in=[(country_code or "").upper()[:2], ""])
    return [
        {
            "code": row.code,
            "name": row.name,
            "term_count_per_year": row.term_count_per_year,
        }
        for row in qs[:30]
    ]


def get_terminology_packs_for_country(country_code: str | None = None) -> list[dict]:
    """Terminology packs for tenant setup."""
    qs = AcademicTerminologyRegistry.objects.filter(is_active=True).order_by(
        "sort_order", "name"
    )
    if country_code:
        qs = qs.filter(country_code__in=[(country_code or "").upper()[:2], ""])
    return [
        {"code": row.code, "name": row.name, "terminology": row.terminology or {}}
        for row in qs[:30]
    ]


DEFAULT_ATTENDANCE_CODES: tuple[dict, ...] = (
    {
        "code": "P",
        "label": "Present",
        "counts_as_present": True,
        "is_excused_absence": False,
    },
    {
        "code": "A",
        "label": "Absent",
        "counts_as_present": False,
        "is_excused_absence": False,
    },
    {
        "code": "T",
        "label": "Tardy",
        "counts_as_present": True,
        "is_excused_absence": False,
    },
    {
        "code": "E",
        "label": "Excused absence",
        "counts_as_present": False,
        "is_excused_absence": True,
    },
)


def get_effective_attendance_codes(school) -> list[dict]:
    """
    Tenant-overridable attendance codes (SOT §0.2.2). If school has TenantAttendanceCode rows,
    those replace defaults entirely.
    """
    from .tenant_registry_models import TenantAttendanceCode

    if school is None:
        return list(DEFAULT_ATTENDANCE_CODES)
    qs = TenantAttendanceCode.objects.filter(
        school_id=getattr(school, "pk", school), is_active=True
    ).order_by("sort_order", "code")
    rows = list(qs)
    if not rows:
        return [dict(x) for x in DEFAULT_ATTENDANCE_CODES]
    return [
        {
            "code": r.code,
            "label": r.label,
            "counts_as_present": r.counts_as_present,
            "is_excused_absence": r.is_excused_absence,
            "metadata": r.metadata or {},
        }
        for r in rows
    ]


def get_effective_fee_types_for_school(school) -> list[dict]:
    """Tenant fee line types merged with global FeeCategoryRegistry names where linked."""
    from .tenant_registry_models import TenantFeeTypeEntry

    if school is None:
        return get_fee_categories()
    qs = (
        TenantFeeTypeEntry.objects.filter(
            school_id=getattr(school, "pk", school), is_active=True
        )
        .select_related("fee_category")
        .order_by("sort_order", "code")
    )
    rows = list(qs)
    if not rows:
        cc = (getattr(school, "country_code", None) or "")[:2]
        return get_fee_categories(country_code=cc or None)
    out = []
    for r in rows:
        out.append(
            {
                "code": r.code,
                "label": r.label,
                "fee_category_code": r.fee_category_id if r.fee_category_id else "",
                "fee_category_name": r.fee_category.name if r.fee_category else "",
                "metadata": r.metadata or {},
            }
        )
    return out
