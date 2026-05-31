from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from django.db.models import Q
from django.utils import timezone

from apps.siteconfig.global_catalog import GlobalGeoCatalog
from apps.siteconfig.models import EducationSystemProfile, RegionConfig


PACK_VERSION = "v1"


# Country-level profile overrides for known systems where generic defaults are weak.
# Keep this intentionally compact; countries not listed get generated baseline packs.
COUNTRY_PACK_OVERRIDES: dict[str, dict[str, dict[str, Any]]] = {
    "CMR": {
        "EN": {
            "name": "Cameroon Anglophone Secondary",
            "term_labels": ["First Term", "Second Term", "Third Term"],
            "grading_scale": "0-20",
            "default_language": "en",
            "subject_seed": [
                {"name": "Mathematics", "category": "GENERAL"},
                {"name": "English Language", "category": "GENERAL"},
                {"name": "Biology", "category": "GENERAL"},
                {"name": "Chemistry", "category": "GENERAL"},
                {"name": "Physics", "category": "GENERAL"},
                {"name": "History", "category": "GENERAL"},
            ],
            "config": {
                "grading_logic": "numeric_0_20",
                "report_template_family": "cameroon",
            },
        },
        "FR": {
            "name": "Cameroon Francophone Secondary",
            "term_labels": ["Trimestre 1", "Trimestre 2", "Trimestre 3"],
            "grading_scale": "0-20",
            "default_language": "fr",
            "subject_seed": [
                {"name": "Mathematiques", "category": "GENERAL"},
                {"name": "Francais", "category": "GENERAL"},
                {"name": "Anglais", "category": "GENERAL"},
                {"name": "Physique", "category": "GENERAL"},
                {"name": "Chimie", "category": "GENERAL"},
                {"name": "Histoire", "category": "GENERAL"},
            ],
            "config": {
                "grading_logic": "numeric_0_20",
                "report_template_family": "cameroon",
            },
        },
    },
    "UGA": {
        "EN": {
            "name": "Uganda National Secondary",
            "term_labels": ["Term I", "Term II", "Term III"],
            "subject_seed": [
                {"name": "Mathematics", "category": "GENERAL"},
                {"name": "English", "category": "GENERAL"},
                {"name": "Biology", "category": "GENERAL"},
                {"name": "Chemistry", "category": "GENERAL"},
                {"name": "Physics", "category": "GENERAL"},
                {"name": "Geography", "category": "GENERAL"},
            ],
            "config": {
                "grading_logic": "percentage",
                "report_template_family": "east_africa",
            },
        }
    },
    "NGA": {
        "EN": {
            "name": "Nigeria National Secondary",
            "term_labels": ["First Term", "Second Term", "Third Term"],
            "subject_seed": [
                {"name": "Mathematics", "category": "GENERAL"},
                {"name": "English", "category": "GENERAL"},
                {"name": "Basic Science", "category": "GENERAL"},
                {"name": "Civic Education", "category": "GENERAL"},
                {"name": "Agricultural Science", "category": "GENERAL"},
            ],
            "config": {
                "grading_logic": "percentage",
                "report_template_family": "west_africa",
            },
        }
    },
    "KEN": {
        "EN": {
            "name": "Kenya National Secondary",
            "term_labels": ["Term 1", "Term 2", "Term 3"],
            "default_language": "sw",
            "subject_seed": [
                {"name": "Mathematics", "category": "GENERAL"},
                {"name": "English", "category": "GENERAL"},
                {"name": "Kiswahili", "category": "GENERAL"},
                {"name": "Biology", "category": "GENERAL"},
                {"name": "Chemistry", "category": "GENERAL"},
            ],
            "config": {
                "grading_logic": "percentage",
                "report_template_family": "east_africa",
            },
        }
    },
    "GBR": {
        "INT": {
            "name": "British / International (UK)",
            "term_labels": ["Michaelmas", "Lent", "Trinity"],
            "grading_scale": "letter",
            "default_language": "en",
            "subject_seed": [
                {"name": "Mathematics", "category": "GENERAL"},
                {"name": "English", "category": "GENERAL"},
                {"name": "Science", "category": "GENERAL"},
                {"name": "History", "category": "GENERAL"},
                {"name": "Geography", "category": "GENERAL"},
            ],
            "config": {
                "grading_logic": "summative",
                "report_template_family": "british",
            },
        }
    },
}


@dataclass(frozen=True)
class ProfileSelectionOption:
    code: str
    name: str
    version: str
    lineage_key: str
    approval_status: str
    region_code: str
    sub_system: str
    is_default: bool
    is_auto_generated: bool
    scope: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "name": self.name,
            "version": self.version,
            "lineage_key": self.lineage_key,
            "approval_status": self.approval_status,
            "region_code": self.region_code,
            "sub_system": self.sub_system,
            "is_default": self.is_default,
            "is_auto_generated": self.is_auto_generated,
            "scope": self.scope,
        }


def normalize_sub_system(value: str | None) -> str:
    raw = (value or "").strip().upper()
    if raw in {
        EducationSystemProfile.SubSystem.ANY,
        EducationSystemProfile.SubSystem.FR,
        EducationSystemProfile.SubSystem.EN,
        EducationSystemProfile.SubSystem.INT,
    }:
        return raw
    return EducationSystemProfile.SubSystem.ANY


def _profile_code(country_code: str, sub_system: str) -> str:
    return f"{country_code.lower()}-{sub_system.lower()}-auto"


def _approved_profiles():
    return EducationSystemProfile.objects.filter(
        is_active=True,
        approval_status=EducationSystemProfile.ApprovalStatus.APPROVED,
    )


def _default_term_labels(
    *, term_count: int, sub_system: str, language: str
) -> list[str]:
    if term_count <= 0:
        return []
    if sub_system == EducationSystemProfile.SubSystem.FR or language.lower().startswith(
        "fr"
    ):
        return [f"Trimestre {idx + 1}" for idx in range(term_count)]
    if term_count == 2:
        return ["Semester 1", "Semester 2"]
    if term_count == 3:
        return ["Term 1", "Term 2", "Term 3"]
    return [f"Period {idx + 1}" for idx in range(term_count)]


def _default_subject_seed(language: str) -> list[dict[str, str]]:
    lang = (language or "en").lower()
    if lang.startswith("fr"):
        return [
            {"name": "Mathematiques", "category": "GENERAL"},
            {"name": "Francais", "category": "GENERAL"},
            {"name": "Sciences", "category": "GENERAL"},
        ]
    return [
        {"name": "Mathematics", "category": "GENERAL"},
        {"name": "English", "category": "GENERAL"},
        {"name": "Science", "category": "GENERAL"},
    ]


def _default_grading_scale(region: RegionConfig, sub_system: str) -> str:
    configured = str(getattr(region, "grading_scale", "") or "").strip()
    if configured:
        return configured
    if sub_system == EducationSystemProfile.SubSystem.FR:
        return "0-20"
    return "0-100"


def ensure_region_for_country(
    country_code: str, timezone_hint: str = "UTC"
) -> RegionConfig | None:
    normalized = GlobalGeoCatalog.normalize_country_code(country_code)
    if not normalized:
        return None
    region = RegionConfig.objects.filter(code=normalized).first()
    if region:
        return region

    defaults = GlobalGeoCatalog.country_defaults(normalized)
    # Academic year start month: prefer the catalog if it has one for this country;
    # otherwise fall back to a hemisphere-aware default. Southern-hemisphere
    # countries (AU, NZ, ZA, etc.) start their year in Jan/Feb, not September.
    _SOUTHERN_HEMISPHERE_CODES = {
        "AU", "NZ", "ZA", "AR", "CL", "UY", "PY", "BO", "PE", "ZW", "ZM",
        "MZ", "MG", "NA", "BW", "SZ", "LS",
    }
    fallback_start_month = 1 if normalized in _SOUTHERN_HEMISPHERE_CODES else 9
    catalog_start = (defaults.get("academic_year_start_month") if isinstance(defaults, dict) else None)
    return RegionConfig.objects.create(
        code=normalized,
        name=defaults["country_name"],
        default_language=defaults["default_language"],
        timezone=defaults["timezone"] or timezone_hint or "UTC",
        date_format=defaults.get("date_format", "DD/MM/YYYY") if isinstance(defaults, dict) else "DD/MM/YYYY",
        grading_scale=defaults.get("grading_scale", "0-100") if isinstance(defaults, dict) else "0-100",
        default_currency=defaults["currency"],
        academic_year_start_month=catalog_start or fallback_start_month,
        term_count_per_year=defaults.get("term_count_per_year", 3) if isinstance(defaults, dict) else 3,
    )


def build_profile_defaults(region: RegionConfig, sub_system: str) -> dict[str, Any]:
    sub = normalize_sub_system(sub_system)
    defaults = GlobalGeoCatalog.country_defaults(region.code)
    language = str(
        getattr(region, "default_language", "") or defaults["default_language"] or "en"
    )
    currency = str(
        getattr(region, "default_currency", "") or defaults["currency"] or "USD"
    )
    timezone_name = str(
        getattr(region, "timezone", "") or defaults["timezone"] or "UTC"
    )
    term_count = int(getattr(region, "term_count_per_year", 3) or 3)
    start_month = int(getattr(region, "academic_year_start_month", 9) or 9)
    country_name = str(
        getattr(region, "name", "") or defaults["country_name"] or region.code
    )
    override = (COUNTRY_PACK_OVERRIDES.get(region.code, {}) or {}).get(sub, {})

    if not override:
        try:
            from apps.governance.academic_pack_bridge import resolve_grading_preset_key
            from apps.siteconfig.education_dna import EDUCATION_DNA_CURRICULUMS

            # v4.00.98 fix: a redundant local import of GlobalGeoCatalog here
            # was making Python treat the module-level GlobalGeoCatalog as a
            # local variable throughout the function, so the use at line 258
            # (well before this block) raised UnboundLocalError when this
            # path was reached.  The module-level import at the top of the
            # file provides GlobalGeoCatalog already; no re-import needed.

            alpha2 = GlobalGeoCatalog.alpha2_for_country(str(region.code or ""))
            preset_key = resolve_grading_preset_key(alpha2 or str(region.code or ""))
            dna = EDUCATION_DNA_CURRICULUMS.get(preset_key) or {}
            grading = dna.get("grading") if isinstance(dna.get("grading"), dict) else {}
            if grading.get("type") == "numeric" and grading.get("max") == 20:
                override = {
                    "grading_scale": "0-20",
                    "config": {"grading_logic": "numeric_0_20", "grading_preset_key": preset_key},
                }
            elif grading.get("type") == "standard_score":
                override = {
                    "grading_scale": "0-100",
                    "config": {
                        "grading_logic": "standard_score",
                        "grading_preset_key": preset_key,
                        "ranking_mode": grading.get("ranking_mode", "standard_score_t"),
                    },
                }
            elif preset_key in ("british_igcse", "west_african_waec"):
                override = {
                    "grading_scale": "letter",
                    "config": {"grading_logic": "alphanumeric", "grading_preset_key": preset_key},
                }
            else:
                override = {
                    "config": {"grading_preset_key": preset_key},
                }
        except (ImportError, AttributeError, TypeError, ValueError):
            override = {}

    name = str(override.get("name") or f"{country_name} Education Pack ({sub})")
    term_labels = override.get(
        "term_labels",
        _default_term_labels(term_count=term_count, sub_system=sub, language=language),
    )
    grading_scale = str(
        override.get("grading_scale") or _default_grading_scale(region, sub)
    )
    subject_seed = override.get("subject_seed") or _default_subject_seed(language)
    config = {
        "pack_source": "auto-country-pack",
        "pack_version": PACK_VERSION,
        "country_code": region.code,
        "generated": True,
    }
    config.update(dict(override.get("config") or {}))

    return {
        "name": name,
        "region": region,
        "sub_system": sub,
        "is_default": True,
        "is_active": True,
        "academic_year_start_month": start_month,
        "term_count_per_year": term_count,
        "term_labels": term_labels,
        "grading_scale": grading_scale,
        "default_language": str(override.get("default_language") or language or "en"),
        "default_currency": str(override.get("default_currency") or currency or "USD"),
        "default_timezone": str(
            override.get("default_timezone") or timezone_name or "UTC"
        ),
        "subject_seed": subject_seed,
        "config": config,
    }


def ensure_country_profile(
    *,
    region_code: str | None = None,
    region: RegionConfig | None = None,
    sub_system: str | None = None,
) -> EducationSystemProfile | None:
    target_sub = normalize_sub_system(sub_system)
    target_region = region
    if target_region is None:
        target_region = ensure_region_for_country(region_code or "")
    if target_region is None:
        return None

    direct = (
        _approved_profiles()
        .filter(
            region=target_region,
            sub_system=target_sub,
        )
        .order_by("-is_default", "name")
        .first()
    )
    if direct:
        return direct

    any_profile = (
        _approved_profiles()
        .filter(
            region=target_region,
            sub_system=EducationSystemProfile.SubSystem.ANY,
        )
        .order_by("-is_default", "name")
        .first()
    )
    if any_profile:
        return any_profile

    profile_code = _profile_code(target_region.code, target_sub)
    defaults = build_profile_defaults(target_region, target_sub)
    defaults.update(
        {
            "lineage_key": profile_code,
            "version": "1.0.0",
            "approval_status": EducationSystemProfile.ApprovalStatus.APPROVED,
            "approved_at": timezone.now(),
        }
    )
    profile, created = EducationSystemProfile.objects.get_or_create(
        code=profile_code,
        defaults=defaults,
    )
    if not created:
        dirty = False
        if not profile.is_active:
            profile.is_active = True
            dirty = True
        if profile.region_id != target_region.code:
            profile.region = target_region
            dirty = True
        if profile.approval_status != EducationSystemProfile.ApprovalStatus.APPROVED:
            profile.approval_status = EducationSystemProfile.ApprovalStatus.APPROVED
            dirty = True
        if not profile.approved_at:
            profile.approved_at = timezone.now()
            dirty = True
        if not profile.lineage_key:
            profile.lineage_key = profile_code
            dirty = True
        if not profile.version:
            profile.version = "1.0.0"
            dirty = True
        if dirty:
            profile.save(
                update_fields=[
                    "is_active",
                    "region",
                    "approval_status",
                    "approved_at",
                    "lineage_key",
                    "version",
                    "updated_at",
                ]
            )
    return profile


def resolve_profile_for_school(
    school,
    *,
    requested_profile_code: str = "",
    auto_create: bool = True,
) -> EducationSystemProfile | None:
    requested = (requested_profile_code or "").strip()
    if requested:
        explicit = _approved_profiles().filter(code=requested).first()
        if explicit:
            return explicit

    profile = EducationSystemProfile.for_school(school)
    if profile or not auto_create:
        return profile

    region_id = getattr(school, "default_region_id", None)
    sub_system = getattr(school, "sub_system", EducationSystemProfile.SubSystem.ANY)
    return ensure_country_profile(region_code=region_id, sub_system=sub_system)


def list_profile_options(
    *,
    country_code: str | None = None,
    sub_system: str | None = None,
    province_id: int | None = None,
) -> list[dict[str, Any]]:
    normalized_country = GlobalGeoCatalog.normalize_country_code(country_code)
    normalized_sub = normalize_sub_system(sub_system)
    if normalized_country and normalized_sub != EducationSystemProfile.SubSystem.ANY:
        ensure_country_profile(
            region_code=normalized_country, sub_system=normalized_sub
        )

    queryset = _approved_profiles()
    if normalized_country:
        queryset = queryset.filter(region__code=normalized_country)
    else:
        queryset = queryset.filter(region__isnull=True)

    if province_id is not None:
        queryset = queryset.filter(
            Q(province_id=province_id) | Q(province__isnull=True)
        )

    if normalized_sub != EducationSystemProfile.SubSystem.ANY:
        queryset = queryset.filter(
            sub_system__in=[normalized_sub, EducationSystemProfile.SubSystem.ANY]
        )

    rows = queryset.select_related("region").order_by(
        "-is_default", "sub_system", "name"
    )
    options = [
        ProfileSelectionOption(
            code=str(row.code),
            name=str(row.name),
            version=str(row.version or "1.0.0"),
            lineage_key=str(row.lineage_key or row.code),
            approval_status=str(row.approval_status),
            region_code=str(row.region_id or ""),
            sub_system=str(row.sub_system),
            is_default=bool(row.is_default),
            is_auto_generated=bool((row.config or {}).get("generated")),
            scope="country" if row.region_id else "global",
        ).as_dict()
        for row in rows
    ]
    if options:
        return options

    if normalized_country:
        # Ensure at least one selector option exists for any valid country.
        created = ensure_country_profile(
            region_code=normalized_country,
            sub_system=normalized_sub,
        )
        if created:
            return [
                ProfileSelectionOption(
                    code=str(created.code),
                    name=str(created.name),
                    region_code=str(created.region_id or ""),
                    sub_system=str(created.sub_system),
                    is_default=bool(created.is_default),
                    is_auto_generated=bool((created.config or {}).get("generated")),
                    scope="country" if created.region_id else "global",
                ).as_dict()
            ]
    return []


def _profile_catalog_description(profile: EducationSystemProfile) -> str:
    labels = [
        str(label).strip()
        for label in (profile.term_labels or [])
        if str(label).strip()
    ]
    term_preview = ", ".join(labels[:3]) if labels else "Default terms"
    grading_scale = str(getattr(profile, "grading_scale", "") or "default")
    return f"{term_preview}; grading {grading_scale}."


def list_template_catalog(
    *,
    country_code: str | None = None,
    sub_system: str | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    normalized_country = GlobalGeoCatalog.normalize_country_code(country_code)
    normalized_sub = normalize_sub_system(sub_system)

    queryset = _approved_profiles().select_related("region")
    if normalized_country:
        queryset = queryset.filter(region__code=normalized_country)
    if normalized_sub != EducationSystemProfile.SubSystem.ANY:
        queryset = queryset.filter(
            sub_system__in=[normalized_sub, EducationSystemProfile.SubSystem.ANY]
        )

    catalog: list[dict[str, Any]] = []
    seen_codes: set[str] = set()
    for row in queryset.order_by("-is_default", "region__name", "name"):
        code = str(row.code)
        if code in seen_codes:
            continue
        seen_codes.add(code)
        catalog.append(
            {
                "code": code,
                "name": str(row.name),
                "description": _profile_catalog_description(row),
                "region_code": str(row.region_id or ""),
                "sub_system": str(row.sub_system),
                "is_default": bool(row.is_default),
                "is_auto_generated": bool((row.config or {}).get("generated")),
            }
        )
        if limit is not None and len(catalog) >= int(limit):
            break
    return catalog


def get_system_blueprint(
    region_id: str | None,
    flavor: str | None = None,
) -> dict[str, Any]:
    """
    Phase Global: Return merged UI/manifest for a region + flavor (sub_system or profile code).
    Used by Environment Discovery and onboarding to preview grading, labels, term structure.
    """
    sub_system = normalize_sub_system(flavor or "ANY")
    profile = None
    if region_id:
        region = RegionConfig.objects.filter(code=region_id).first()
        if region:
            profile = ensure_country_profile(region=region, sub_system=sub_system)
    if not profile:
        return {
            "primary_language": "en",
            "grading_scale": "0-100",
            "term_labels": ["Term 1", "Term 2", "Term 3"],
            "report_template_family": "global",
            "labels_map": {},
            "modality": "in_person",
        }
    cfg = getattr(profile, "config", None) or {}
    return {
        "primary_language": getattr(profile, "default_language", None) or "en",
        "grading_scale": getattr(profile, "grading_scale", None) or "0-100",
        "term_labels": profile.normalized_term_labels(),
        "report_template_family": (cfg.get("report_template_family") or "global"),
        "labels_map": dict(cfg.get("labels_map") or {}),
        "modality": str(cfg.get("modality") or "in_person"),
    }
