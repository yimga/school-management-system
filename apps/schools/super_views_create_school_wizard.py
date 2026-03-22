"""
Create School wizard (BR-12 split from super_views).
"""

from django.shortcuts import render, redirect
from django.views.decorators.http import require_http_methods

from apps.registries.models import (
    EducationLevelRegistry,
    EducationSystemTypeRegistry,
)
from apps.registries.services import (
    ensure_registry_baseline,
    list_country_choices,
    list_sector_system_types_14_22,
)
from apps.siteconfig.education_profile_engine import (
    list_template_catalog,
    list_profile_options,
)
from apps.siteconfig.global_catalog import GlobalGeoCatalog
from apps.platform_runtime.helpers import get_platform_defaults
from apps.siteconfig.tenant_config import REGIONAL_POLICY_PACKS

from .models import School
from .super_views_helpers import canonical_country_alpha2 as _canonical_country_alpha2

# Pack code (from Geography / REGIONAL_POLICY_PACKS) -> default country alpha-2 for wizard pre-select
_CREATE_SCHOOL_PACK_TO_COUNTRY = {
    "US": "US",
    "CAN": "CA",
    "GBR": "GB",
    "EU": "FR",
    "BRA": "BR",
    "WAEC": "NG",
    "AFR_FR": "CM",
    "LCA": "UG",
    "ASIA": "SG",
    "LATAM_ES": "CO",
    "MENA": "AE",
    "AUS": "AU",
    "NZL": "NZ",
}


@require_http_methods(["GET", "POST"])
def create_school_wizard(request):
    """Multi-step wizard: Step 1 identity, Step 2 region, Step 3 branding. POST submits to API."""
    from apps.global_registries.models import RegionConfig, WeatherLocation
    from apps.siteconfig.models import default_header_weather_config

    if request.method == "POST":
        # Wizard form submitted via JS to api_create_school; this is fallback or redirect
        return redirect("super:api_create_school")

    ensure_registry_baseline()
    regions = RegionConfig.objects.all().order_by("name")
    defaults = default_header_weather_config()
    default_country_code = _canonical_country_alpha2(
        defaults.get("header_weather_country_code")
        or get_platform_defaults(use_db=False)["region_code"]
    )
    initial_pack = None
    initial_pack_name = None
    pack_param = request.GET.get("pack") or request.GET.get("region")
    if pack_param and pack_param in REGIONAL_POLICY_PACKS:
        override = _CREATE_SCHOOL_PACK_TO_COUNTRY.get(pack_param)
        if override:
            default_country_code = override
        initial_pack = pack_param
        initial_pack_name = REGIONAL_POLICY_PACKS[pack_param].get("name", pack_param)
    countries = list_country_choices()
    known_codes = {row["code"] for row in countries}
    if default_country_code not in known_codes and countries:
        default_country_code = countries[0]["code"]
    default_country_alpha3 = GlobalGeoCatalog.normalize_country_code(
        default_country_code
    )
    cities = GlobalGeoCatalog.search_cities(
        country_code=default_country_alpha3,
        limit=180,
    )
    default_sub_system = School.SubSystem.EN
    education_profiles = list_profile_options(
        country_code=default_country_alpha3,
        sub_system=default_sub_system,
    )
    education_levels = EducationLevelRegistry.objects.filter(is_active=True).order_by(
        "sort_order", "global_name"
    )
    education_system_types = EducationSystemTypeRegistry.objects.filter(
        is_active=True
    ).order_by("sort_order", "name")
    sector_types_14_22 = list_sector_system_types_14_22()
    # S2: One-click education templates (British/WAEC/Vocational) — same as API config/education-templates
    education_templates_standard = [
        {
            "code": "BRITISH_IGCSE",
            "name": "British / IGCSE",
            "description": "Michaelmas, Lent, Trinity; A*–G or 9–1.",
        },
        {
            "code": "WAEC",
            "name": "West African (WAEC)",
            "description": "First, Second, Third term; A1–F9; CA 30% + Exam 70%.",
        },
        {
            "code": "FRANCOPHONE_BAC",
            "name": "Francophone (Bac)",
            "description": "Trimestre 1–3; 20-point scale.",
        },
        {
            "code": "VOCATIONAL",
            "name": "Vocational / Trade",
            "description": "Competency checklists; clock hours; skill badges.",
        },
        {
            "code": "IB",
            "name": "International Baccalaureate",
            "description": "IB DP/MYP; 1–7 scale; summative weighting.",
        },
    ]
    catalog_templates = list_template_catalog(
        country_code=default_country_alpha3,
        sub_system=default_sub_system,
        limit=8,
    )
    if catalog_templates:
        education_templates_standard = catalog_templates
    parent_school_id = (request.GET.get("parent_school_id") or "").strip()
    parent_school_name = None
    if parent_school_id:
        parent_school_obj = School.objects.filter(
            pk=parent_school_id, is_active=True
        ).first()
        if parent_school_obj:
            parent_school_name = parent_school_obj.name
        else:
            parent_school_id = ""
    if not countries or not cities:
        # Backward-compatible fallback when optional catalog dependencies are unavailable.
        WeatherLocation.ensure_seed_data()
        locations = list(
            WeatherLocation.objects.select_related("region")
            .filter(is_active=True)
            .order_by("region__name", "sort_order", "city")
        )
        countries = []
        seen = set()
        for loc in locations:
            if loc.region_id in seen:
                continue
            seen.add(loc.region_id)
            countries.append(
                {
                    "code": _canonical_country_alpha2(loc.region_id) or loc.region_id,
                    "code_alpha2": _canonical_country_alpha2(loc.region_id) or "",
                    "code_alpha3": loc.region_id,
                    "name": loc.region.name,
                    "timezone": loc.region.timezone,
                }
            )
        cities = [
            {
                "id": str(loc.pk),
                "country_code": _canonical_country_alpha2(loc.region_id)
                or loc.region_id,
                "country_code_alpha3": loc.region_id,
                "city": loc.city,
                "label": loc.display_label,
                "timezone": loc.timezone or loc.region.timezone or "UTC",
                "latitude": float(loc.latitude),
                "longitude": float(loc.longitude),
            }
            for loc in locations
            if not default_country_alpha3 or loc.region_id == default_country_alpha3
        ]
    return render(
        request,
        "schools/super_create_school_wizard.html",
        {
            "regions": regions,
            "countries": countries,
            "cities": cities,
            "default_country_code": default_country_code
            or defaults.get("header_weather_country_code")
            or get_platform_defaults(use_db=False)["region_code"],
            "default_sub_system": default_sub_system,
            "education_profiles": education_profiles,
            "education_levels": education_levels,
            "education_system_types": education_system_types,
            "sector_types_14_22": sector_types_14_22,
            "education_templates_standard": education_templates_standard,
            "school_admin_edit_template": "",
            "geo_city_search_min_chars": 1,
            "initial_pack": initial_pack,
            "initial_pack_name": initial_pack_name,
            "parent_school_id": parent_school_id,
            "parent_school_name": parent_school_name,
        },
    )
