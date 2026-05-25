"""
Geo, education profile, system blueprint, and plans JSON APIs for the control plane
and Create School wizard (BR-12 extraction from super_views).
"""

from __future__ import annotations

from decimal import Decimal

from django.http import JsonResponse
from django.views.decorators.http import require_http_methods

from apps.registries.models import SubdivisionRegistry
from apps.registries.services import ensure_registry_baseline, list_subdivision_choices
from apps.siteconfig.education_profile_engine import list_profile_options
from apps.siteconfig.global_catalog import GlobalGeoCatalog

from .models import School
from .super_views_helpers import canonical_country_alpha2 as _canonical_country_alpha2
from apps.platform_runtime.operator_identity import (
    PLATFORM_SCOPE_TENANT_READ,
    require_platform_scope,
)


def _clamp_int(value, default: int, *, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(maximum, parsed))


@require_http_methods(["GET"])
@require_platform_scope(PLATFORM_SCOPE_TENANT_READ)
def api_geo_cities(request):
    country_code = GlobalGeoCatalog.normalize_country_code(
        request.GET.get("country_code")
    )
    query = (request.GET.get("q") or "").strip()
    limit = _clamp_int(request.GET.get("limit"), 120, minimum=10, maximum=500)
    cities = GlobalGeoCatalog.search_cities(
        country_code=country_code, query=query, limit=limit
    )
    return JsonResponse(
        {"country_code": country_code, "query": query, "cities": cities}
    )


@require_http_methods(["GET"])
@require_platform_scope(PLATFORM_SCOPE_TENANT_READ)
def api_geo_timezones(request):
    country_code = GlobalGeoCatalog.normalize_country_code(
        request.GET.get("country_code")
    )
    query = (request.GET.get("q") or "").strip()
    limit = _clamp_int(request.GET.get("limit"), 500, minimum=10, maximum=2000)
    timezones = GlobalGeoCatalog.list_timezones(
        country_code=country_code, query=query, limit=limit
    )
    return JsonResponse(
        {"country_code": country_code, "query": query, "timezones": timezones}
    )


@require_http_methods(["GET"])
@require_platform_scope(PLATFORM_SCOPE_TENANT_READ)
def api_provinces(request):
    """List canonical subdivisions for a country; keeps `provinces` key for compatibility."""
    ensure_registry_baseline()
    country_code = (request.GET.get("country_code") or "").strip()
    subdivisions = list_subdivision_choices(country_code)
    alpha2 = _canonical_country_alpha2(country_code)
    return JsonResponse(
        {
            "country_code": alpha2,
            "provinces": subdivisions,
            "subdivisions": subdivisions,
        }
    )


@require_http_methods(["GET"])
@require_platform_scope(PLATFORM_SCOPE_TENANT_READ)
def api_education_profiles(request):
    country_code = GlobalGeoCatalog.normalize_country_code(
        request.GET.get("country_code")
    )
    sub_system = (request.GET.get("sub_system") or School.SubSystem.EN).strip().upper()
    valid_subsystems = {School.SubSystem.EN, School.SubSystem.FR, School.SubSystem.INT}
    if sub_system not in valid_subsystems:
        sub_system = School.SubSystem.EN
    province_id = request.GET.get("province_id")
    subdivision_id = request.GET.get("subdivision_id")
    if subdivision_id not in (None, ""):
        try:
            subdivision = SubdivisionRegistry.objects.filter(
                pk=int(subdivision_id)
            ).first()
        except (TypeError, ValueError):
            subdivision = None
        if subdivision:
            province_id = (subdivision.metadata or {}).get("legacy_province_id")
    if province_id is not None and province_id != "":
        try:
            province_id = int(province_id)
        except (TypeError, ValueError):
            province_id = None
    else:
        province_id = None

    profiles = list_profile_options(
        country_code=country_code,
        sub_system=sub_system,
        province_id=province_id,
    )
    return JsonResponse(
        {
            "country_code": country_code,
            "sub_system": sub_system,
            "province_id": province_id,
            "profiles": profiles,
            "auto_option": {
                "code": "",
                "name": "Auto by Country and Sub-system",
                "description": "Recommended. Provisioning resolves the best profile automatically.",
            },
        }
    )


@require_http_methods(["GET"])
@require_platform_scope(PLATFORM_SCOPE_TENANT_READ)
def api_system_blueprint(request):
    """
    Phase Global: Environment Discovery — get merged blueprint for region + flavor.
    GET ?region_id=CMR&flavor=EN returns primary_language, grading_scale, term_labels, etc.
    """
    from apps.siteconfig.education_profile_engine import get_system_blueprint

    region_id = (request.GET.get("region_id") or "").strip() or None
    flavor = (request.GET.get("flavor") or "").strip() or None
    blueprint = get_system_blueprint(region_id=region_id, flavor=flavor)
    return JsonResponse(blueprint)


@require_http_methods(["GET"])
@require_platform_scope(PLATFORM_SCOPE_TENANT_READ)
def api_plans_configurator(request):
    """
    Plan Configurator API (Phase E): GET plans, addons, country_multiplier.
    Same contract for onboarding billing step and PlanConfigurator component.
    Version: 1.
    """
    from apps.plans_entitlements.models import CountryMultiplier, Plan, PlanAddon

    country_code = GlobalGeoCatalog.normalize_country_code(
        (request.GET.get("country_code") or "").strip()
    )
    plans = []
    for p in Plan.objects.filter(is_active=True).order_by("name"):
        plans.append(
            {
                "id": p.pk,
                "name": p.name,
                "slug": p.slug,
                "billing_model": p.billing_model or "FLAT",
                "base_price": float(p.base_price) if p.base_price is not None else None,
                "price_per_student": float(p.price_per_student)
                if p.price_per_student is not None
                else None,
                "tier_rules": p.tier_rules if isinstance(p.tier_rules, list) else [],
                "max_students": p.max_students,
                "max_staff": p.max_staff,
                "included_features": p.included_features or [],
            }
        )
    addons = []
    for a in PlanAddon.objects.filter(is_active=True).order_by("name"):
        addons.append(
            {
                "code": a.code,
                "name": a.name,
                "price": float(a.price),
            }
        )
    multiplier = Decimal("1")
    if country_code:
        row = CountryMultiplier.objects.filter(
            country_code=country_code, is_active=True
        ).first()
        if row:
            multiplier = row.multiplier
    return JsonResponse(
        {
            "version": 1,
            "country_code": country_code or "",
            "country_multiplier": float(multiplier),
            "plans": plans,
            "addons": addons,
        }
    )
