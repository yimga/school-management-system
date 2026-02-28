"""
Super Admin views: dashboard (list schools) and Create School wizard.
Access restricted to SUPERADMIN or is_superuser via TenantSuperAdminRequiredMiddleware.
"""
from django.db.models import Count
from django.db.models import OuterRef, Subquery
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import NoReverseMatch, reverse
from django.views.decorators.http import require_http_methods, require_POST
from django.http import JsonResponse

from apps.siteconfig.education_profile_engine import (
    ensure_region_for_country as ensure_region_for_country_record,
    list_profile_options,
)
from apps.siteconfig.global_catalog import GlobalGeoCatalog
from apps.siteconfig.models import EducationSystemProfile
from apps.siteconfig.tenant_config import apply_tenant_settings_overrides
from .models import School, SchoolProvisioningEvent, TenantApiUsage, TenantQuotaLimit


def _safe_school_admin_change_url(school_id) -> str:
    try:
        return reverse("admin:schools_school_change", args=[school_id])
    except NoReverseMatch:
        return ""
    except Exception:
        return ""


def _safe_school_timeline_url(school_id) -> str:
    try:
        return reverse("super:api_school_timeline", args=[school_id])
    except NoReverseMatch:
        return ""
    except Exception:
        return ""


def _clamp_int(value, default: int, *, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(maximum, parsed))


def _ensure_region_for_country(country_code: str, timezone_hint: str = "UTC"):
    return ensure_region_for_country_record(country_code, timezone_hint=timezone_hint)


def _safe_registry_url():
    """URL to Global Registry (EducationSystemProfile CRUD in admin). Phase H."""
    try:
        return reverse("admin:siteconfig_educationsystemprofile_changelist")
    except NoReverseMatch:
        return ""


def super_dashboard(request):
    """List all schools with basic stats. Phase E: Financial Bento. Phase H: Registry link, selected education systems."""
    from django.db.models import Sum
    from django.utils import timezone
    from apps.siteconfig.models import RevenueSnapshot

    latest_event_query = SchoolProvisioningEvent.objects.filter(school_id=OuterRef("pk")).order_by("-created_at", "-id")
    schools = list(
        School.objects.all()
        .prefetch_related("tenant_systems__system")
        .order_by("name")
        .annotate(member_count=Count("memberships"))
        .annotate(student_count=Count("student_profiles", distinct=True))
        .annotate(teacher_count=Count("teacher_profiles", distinct=True))
        .annotate(latest_event_type=Subquery(latest_event_query.values("event_type")[:1]))
        .annotate(latest_event_status=Subquery(latest_event_query.values("status")[:1]))
        .annotate(latest_event_created_at=Subquery(latest_event_query.values("created_at")[:1]))
    )
    for school in schools:
        school.admin_edit_url = _safe_school_admin_change_url(school.pk)
        school.timeline_url = _safe_school_timeline_url(school.pk)
        school.sync_repair_url = reverse("super:sync_repair", args=[school.pk])
        school.selected_systems = [ts.system.name for ts in getattr(school, "tenant_systems", []) if getattr(ts, "system", None)]

    # Phase E: Financial Mission Control / Bento (latest month); resilient if RevenueSnapshot not migrated
    total_mrr = total_waived = waiver_percentage = 0
    revenue_by_country = []
    billing_model_breakdown = []
    first_of_month = timezone.now().date().replace(day=1)
    try:
        snapshots = RevenueSnapshot.objects.filter(snapshot_date=first_of_month)
        agg = snapshots.aggregate(total_actual=Sum("actual_revenue"), total_waived=Sum("waived_amount"))
        total_mrr = (agg["total_actual"] or 0)
        total_waived = (agg["total_waived"] or 0)
        total_all = total_mrr + total_waived
        waiver_percentage = (float(total_waived) / float(total_all) * 100) if total_all else 0
        revenue_by_country = list(
            snapshots.values("country_code")
            .annotate(actual=Sum("actual_revenue"), waived=Sum("waived_amount"))
            .order_by("-actual", "-waived")[:20]
        )
        billing_model_breakdown = list(
            snapshots.values("billing_model")
            .annotate(count=Count("id"), actual=Sum("actual_revenue"), waived=Sum("waived_amount"))
            .order_by("-actual", "-waived")
        )
    except Exception:
        pass

    # Phase H optional: approval workflow — count and list pending schools
    pending_schools = list(
        School.objects.filter(is_approved=False)
        .prefetch_related("tenant_systems__system")
        .order_by("-created_at")
        .annotate(member_count=Count("memberships"))
        .annotate(student_count=Count("student_profiles", distinct=True))
    )
    for school in pending_schools:
        school.admin_edit_url = _safe_school_admin_change_url(school.pk)
        school.timeline_url = _safe_school_timeline_url(school.pk)
        school.selected_systems = [ts.system.name for ts in getattr(school, "tenant_systems", []) if getattr(ts, "system", None)]
    pending_approval_count = len(pending_schools)

    # Section 8.7–8.8: Health / resource hogs (PostgreSQL table sizes)
    health_top_tables = []
    health_schema_stats = []
    try:
        from .health_utils import get_top_tables_by_size, get_global_health_stats
        health_top_tables = get_top_tables_by_size(limit=10)
        health_schema_stats = get_global_health_stats()
    except Exception:
        pass

    return render(
        request,
        "schools/super_dashboard.html",
        {
            "schools": schools,
            "pending_schools": pending_schools,
            "pending_approval_count": pending_approval_count,
            "total_mrr": total_mrr,
            "total_waived": total_waived,
            "waiver_percentage": round(waiver_percentage, 1),
            "revenue_by_country": revenue_by_country,
            "billing_model_breakdown": billing_model_breakdown,
            "revenue_snapshot_month": first_of_month,
            "registry_url": _safe_registry_url(),
            "health_top_tables": health_top_tables,
            "health_schema_stats": health_schema_stats,
        },
    )


def super_usage(request):
    """Plan I: Per-tenant API usage and quota limits for super-admin billing/health."""
    from django.db.models import Sum
    schools = list(
        School.objects.filter(is_active=True)
        .annotate(student_count=Count("student_profiles", distinct=True))
        .order_by("name")
    )
    school_ids = [s.pk for s in schools]
    usage_agg = {
        (r["school_id"], r["limit_type"]): r["total"]
        for r in TenantApiUsage.objects.filter(school_id__in=school_ids)
        .values("school_id", "limit_type")
        .annotate(total=Sum("request_count"))
    }
    quotas = {}
    for q in TenantQuotaLimit.objects.filter(school_id__in=school_ids, is_active=True).values(
        "school_id", "limit_type", "limit_value", "period_days"
    ):
        quotas.setdefault(q["school_id"], []).append(q)
    for school in schools:
        school.api_usage = {k: v for (sid, k), v in usage_agg.items() if sid == school.pk}
        school.quota_limits = quotas.get(school.pk, [])
        school.admin_edit_url = _safe_school_admin_change_url(school.pk)
    return render(
        request,
        "schools/super_usage.html",
        {"schools": schools},
    )


def billing_dashboard(request):
    """Plan X: Billing dashboard — trial schools, trial_end_date, usage; Stripe integration via webhooks (see docs)."""
    from django.db.models import Sum
    from django.utils import timezone
    trial_schools = list(
        School.objects.filter(is_active=True, billing_type=School.BillingType.FREE_TRIAL)
        .annotate(student_count=Count("student_profiles", distinct=True))
        .order_by("trial_end_date", "name")
    )
    school_ids = [s.pk for s in trial_schools]
    usage_agg = {}
    if school_ids:
        for r in TenantApiUsage.objects.filter(school_id__in=school_ids).values("school_id").annotate(total=Sum("request_count")):
            usage_agg[r["school_id"]] = r["total"]
    for school in trial_schools:
        school.api_requests = usage_agg.get(school.pk, 0)
        school.admin_edit_url = _safe_school_admin_change_url(school.pk)
        school.trial_expired = school.trial_end_date and school.trial_end_date < timezone.now().date()
    return render(
        request,
        "schools/billing_dashboard.html",
        {
            "trial_schools": trial_schools,
            "usage_url": reverse("super:usage"),
        },
    )


@require_http_methods(["GET", "POST"])
def create_school_wizard(request):
    """Multi-step wizard: Step 1 identity, Step 2 region, Step 3 branding. POST submits to API."""
    from apps.siteconfig.models import (
        RegionConfig,
        WeatherLocation,
        default_header_weather_config,
    )

    if request.method == "POST":
        # Wizard form submitted via JS to api_create_school; this is fallback or redirect
        return redirect("super:api_create_school")

    regions = RegionConfig.objects.all().order_by("name")
    defaults = default_header_weather_config()
    default_country_code = GlobalGeoCatalog.normalize_country_code(
        defaults.get("header_weather_country_code", "CMR")
    )
    countries = GlobalGeoCatalog.list_countries()
    known_codes = {row["code"] for row in countries}
    if default_country_code not in known_codes and countries:
        default_country_code = countries[0]["code"]
    cities = GlobalGeoCatalog.search_cities(
        country_code=default_country_code,
        limit=180,
    )
    default_sub_system = School.SubSystem.EN
    education_profiles = list_profile_options(
        country_code=default_country_code,
        sub_system=default_sub_system,
    )
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
            countries.append({"code": loc.region_id, "name": loc.region.name, "timezone": loc.region.timezone})
        cities = [
            {
                "id": str(loc.pk),
                "country_code": loc.region_id,
                "city": loc.city,
                "label": loc.display_label,
                "timezone": loc.timezone or loc.region.timezone or "UTC",
                "latitude": float(loc.latitude),
                "longitude": float(loc.longitude),
            }
            for loc in locations
            if not default_country_code or loc.region_id == default_country_code
        ]
    return render(
        request,
        "schools/super_create_school_wizard.html",
        {
            "regions": regions,
            "countries": countries,
            "cities": cities,
            "default_country_code": default_country_code or defaults.get("header_weather_country_code", "CMR"),
            "default_sub_system": default_sub_system,
            "education_profiles": education_profiles,
            "school_admin_edit_template": _safe_school_admin_change_url("00000000-0000-0000-0000-000000000000"),
            "geo_city_search_min_chars": 1,
        },
    )


@require_http_methods(["GET"])
def api_geo_cities(request):
    country_code = GlobalGeoCatalog.normalize_country_code(request.GET.get("country_code"))
    query = (request.GET.get("q") or "").strip()
    limit = _clamp_int(request.GET.get("limit"), 120, minimum=10, maximum=500)
    cities = GlobalGeoCatalog.search_cities(country_code=country_code, query=query, limit=limit)
    return JsonResponse({"country_code": country_code, "query": query, "cities": cities})


@require_http_methods(["GET"])
def api_geo_timezones(request):
    country_code = GlobalGeoCatalog.normalize_country_code(request.GET.get("country_code"))
    query = (request.GET.get("q") or "").strip()
    limit = _clamp_int(request.GET.get("limit"), 500, minimum=10, maximum=2000)
    timezones = GlobalGeoCatalog.list_timezones(country_code=country_code, query=query, limit=limit)
    return JsonResponse({"country_code": country_code, "query": query, "timezones": timezones})


@require_http_methods(["GET"])
def api_provinces(request):
    """Phase B: List provinces/states for a country (for wizard and systems filter)."""
    country_code = GlobalGeoCatalog.normalize_country_code(request.GET.get("country_code") or "")
    if not country_code:
        return JsonResponse({"country_code": "", "provinces": []})
    from apps.siteconfig.models import RegionConfig, Province
    region = RegionConfig.objects.filter(code=country_code).first()
    if not region:
        return JsonResponse({"country_code": country_code, "provinces": []})
    provinces = list(
        Province.objects.filter(region=region)
        .order_by("name")
        .values("id", "code", "name")
    )
    return JsonResponse({"country_code": country_code, "provinces": provinces})


@require_http_methods(["GET"])
def api_education_profiles(request):
    country_code = GlobalGeoCatalog.normalize_country_code(request.GET.get("country_code"))
    sub_system = (request.GET.get("sub_system") or School.SubSystem.EN).strip().upper()
    valid_subsystems = {School.SubSystem.EN, School.SubSystem.FR, School.SubSystem.INT}
    if sub_system not in valid_subsystems:
        sub_system = School.SubSystem.EN
    province_id = request.GET.get("province_id")
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
def api_plans_configurator(request):
    """
    Plan Configurator API (Phase E): GET plans, addons, country_multiplier.
    Same contract for onboarding billing step and PlanConfigurator component.
    Version: 1.
    """
    from apps.siteconfig.models import Plan, PlanAddon, CountryMultiplier
    from decimal import Decimal

    country_code = (request.GET.get("country_code") or "").strip().upper()[:3]
    plans = []
    for p in Plan.objects.filter(is_active=True).order_by("name"):
        plans.append({
            "id": p.pk,
            "name": p.name,
            "slug": p.slug,
            "billing_model": p.billing_model or "FLAT",
            "base_price": float(p.base_price) if p.base_price is not None else None,
            "price_per_student": float(p.price_per_student) if p.price_per_student is not None else None,
            "tier_rules": p.tier_rules if isinstance(p.tier_rules, list) else [],
            "max_students": p.max_students,
            "max_staff": p.max_staff,
            "included_features": p.included_features or [],
        })
    addons = []
    for a in PlanAddon.objects.filter(is_active=True).order_by("name"):
        addons.append({
            "code": a.code,
            "name": a.name,
            "price": float(a.price),
        })
    multiplier = Decimal("1")
    if country_code:
        row = CountryMultiplier.objects.filter(country_code=country_code, is_active=True).first()
        if row:
            multiplier = row.multiplier
    return JsonResponse({
        "version": 1,
        "country_code": country_code or "",
        "country_multiplier": float(multiplier),
        "plans": plans,
        "addons": addons,
    })


@require_http_methods(["GET"])
def api_school_timeline(request, school_id):
    school = get_object_or_404(School, id=school_id)
    limit = _clamp_int(request.GET.get("limit"), 80, minimum=1, maximum=500)
    events = list(
        SchoolProvisioningEvent.objects.filter(school=school)
        .order_by("-created_at", "-id")
        .values("event_type", "status", "message", "payload", "created_at")[:limit]
    )
    for event in events:
        created_at = event.get("created_at")
        event["created_at"] = created_at.isoformat() if created_at else ""
    return JsonResponse(
        {
            "school_id": str(school.id),
            "school_name": school.name,
            "events": events,
        }
    )


@require_http_methods(["POST"])
def api_approve_school(request, school_id):
    """Phase H optional: Set school is_approved=True. Super Admin only."""
    school = get_object_or_404(School, id=school_id)
    school.is_approved = True
    school.save(update_fields=["is_approved", "updated_at"])
    return JsonResponse({"ok": True, "school_id": str(school.id), "message": "School approved."})


def _slug_from_name(name: str) -> str:
    """W1-1: Derive URL-safe slug from school name for minimal create path."""
    import re
    s = (name or "").strip().lower()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s[:120] if s else "school"


@require_POST
def api_create_school(request):
    """
    Validate payload, create School row (is_active=False), enqueue provisioning task.
    Returns 202 + job_id or 400 with errors.
    W1-1: Minimal path: name, contact_email, country_code (optional); slug/subdomain derived from name when omitted.
    """
    import json

    try:
        data = json.loads(request.body) if request.body else {}
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    name = (data.get("name") or "").strip()
    slug = (data.get("slug") or "").strip().lower().replace(" ", "-")
    if not slug and name:
        slug = _slug_from_name(name)
    subdomain = (data.get("subdomain") or slug or "").strip().lower()
    contact_email = (data.get("contact_email") or "").strip()
    region_code = GlobalGeoCatalog.normalize_country_code((data.get("region_code") or "").strip())
    country_code = GlobalGeoCatalog.normalize_country_code(
        (data.get("country_code") or region_code or "").strip()
    )
    city_id = (data.get("city_id") or "").strip()
    sub_system = (data.get("sub_system") or School.SubSystem.EN).strip().upper()
    valid_subsystems = {School.SubSystem.EN, School.SubSystem.FR, School.SubSystem.INT}
    if sub_system not in valid_subsystems:
        sub_system = School.SubSystem.EN
    education_profile_code = (data.get("education_profile_code") or "").strip()
    education_system_ids = data.get("education_system_ids")  # Phase B: list of profile codes (multi-select)
    if not isinstance(education_system_ids, list):
        education_system_ids = []
    education_system_ids = [str(x).strip() for x in education_system_ids if x]
    province_id = data.get("province_id")  # Phase B: optional province for geo filtering
    if province_id is not None and province_id != "":
        try:
            province_id = int(province_id)
        except (TypeError, ValueError):
            province_id = None
    primary_color = (data.get("primary_color") or "#0d6efd").strip()
    accent_color = (data.get("accent_color") or "#198754").strip()
    theme_choice = (data.get("theme_choice") or "UNFOLD").strip().upper()
    if theme_choice not in {"UNFOLD", "JAZZMIN", "SNEAT"}:
        theme_choice = "UNFOLD"
    custom_domain = (data.get("custom_domain") or "").strip()
    plan_id = data.get("plan_id")
    if plan_id is not None and plan_id != "":
        try:
            plan_id = int(plan_id)
        except (TypeError, ValueError):
            plan_id = None
    addons = data.get("addons")
    if not isinstance(addons, list):
        addons = []

    if not subdomain and slug:
        subdomain = slug
    errors = []
    if not name:
        errors.append("name is required")
    # W1-1: slug optional; derived from name when omitted.
    if not slug and name:
        slug = _slug_from_name(name)
    if not slug:
        errors.append("slug could not be derived from name; provide slug or name")
    # W1-3: Contact email required for provisioning and welcome email.
    if not contact_email:
        errors.append("contact_email is required")

    if errors:
        return JsonResponse({"errors": errors}, status=400)

    if School.objects.filter(slug=slug).exists():
        return JsonResponse({"errors": ["slug already exists"]}, status=400)
    if subdomain and School.objects.filter(subdomain=subdomain).exists():
        return JsonResponse({"errors": ["subdomain already exists"]}, status=400)

    explicit_profile = None
    if education_profile_code:
        explicit_profile = EducationSystemProfile.objects.filter(
            code=education_profile_code,
            is_active=True,
            approval_status=EducationSystemProfile.ApprovalStatus.APPROVED,
        ).first()
        if explicit_profile is None:
            errors.append("education_profile_code is invalid")
        elif explicit_profile.sub_system not in {
            EducationSystemProfile.SubSystem.ANY,
            sub_system,
        }:
            errors.append("education_profile_code does not match selected sub-system")
    if errors:
        return JsonResponse({"errors": errors}, status=400)

    from apps.siteconfig.models import RegionConfig, WeatherLocation
    default_region = None
    selected_city = GlobalGeoCatalog.get_city(city_id, country_code=country_code)
    selected_location = None
    if city_id and selected_city is None:
        try:
            selected_location = (
                WeatherLocation.objects.select_related("region")
                .filter(pk=int(city_id), is_active=True)
                .first()
            )
        except (TypeError, ValueError):
            selected_location = None
    if selected_location and country_code and selected_location.region_id != country_code:
        selected_location = None
    if selected_city:
        country_code = selected_city["country_code"]
        default_region = _ensure_region_for_country(country_code, selected_city.get("timezone") or "UTC")
    elif selected_location:
        default_region = selected_location.region
        country_code = selected_location.region_id
    if default_region is None and country_code:
        default_region = RegionConfig.objects.filter(code=country_code).first() or _ensure_region_for_country(country_code)
    if default_region is None and region_code:
        default_region = RegionConfig.objects.filter(code=region_code).first() or _ensure_region_for_country(region_code)
    if default_region is None and explicit_profile and explicit_profile.region_id:
        default_region = explicit_profile.region
        country_code = explicit_profile.region_id
    resolved_timezone = (
        (selected_city.get("timezone") if selected_city else "")
        or (selected_location.timezone if selected_location else "")
        or (explicit_profile.default_timezone if explicit_profile else "")
        or (default_region.timezone if default_region else "")
        or "UTC"
    )
    location_payload = {
        "country_code": country_code or (default_region.code if default_region else ""),
        "city": "",
        "label": "",
        "timezone": resolved_timezone,
        "city_id": city_id or "",
    }
    if selected_city:
        location_payload.update(
            {
                "city": selected_city.get("city", ""),
                "label": selected_city.get("label", ""),
                "latitude": selected_city.get("latitude"),
                "longitude": selected_city.get("longitude"),
            }
        )
    elif selected_location:
        location_payload.update(
            {
                "city": selected_location.city,
                "label": selected_location.display_label,
                "latitude": float(selected_location.latitude),
                "longitude": float(selected_location.longitude),
            }
        )

    school_settings_overrides = {
        "contact_email": contact_email,
        "provisioning": {
            "logo_uploaded": False,
            "education_profile_mode": "explicit" if explicit_profile else "auto",
            "education_system_ids": education_system_ids,
            "province_id": province_id,
        },
        "education_profile_code": explicit_profile.code if explicit_profile else "",
        "location": location_payload,
        "custom_domain": {
            "hostname": custom_domain or "",
            "status": "pending_verification" if custom_domain else "not_configured",
            "verified": False,
        },
    }

    create_kw = dict(
        name=name,
        slug=slug,
        subdomain=subdomain or slug,
        sub_system=sub_system,
        default_region=default_region,
        timezone=resolved_timezone,
        primary_color=primary_color,
        accent_color=accent_color,
        custom_domain=custom_domain or "",
        is_active=False,
        is_approved=not (__import__("os").getenv("ENABLE_SCHOOL_APPROVAL_WORKFLOW", "").strip().lower() in ("1", "true", "yes")),
        settings={},
    )
    if hasattr(School, "theme_choice"):
        create_kw["theme_choice"] = theme_choice
    if plan_id and hasattr(School, "plan_id"):
        from apps.siteconfig.models import Plan
        if Plan.objects.filter(pk=plan_id, is_active=True).exists():
            create_kw["plan_id"] = plan_id
    if addons and hasattr(School, "addons"):
        addons = [str(x).strip() for x in addons if x]
        create_kw["addons"] = addons
    school = School.objects.create(**create_kw)
    apply_tenant_settings_overrides(
        school=school,
        overrides=school_settings_overrides,
        actor_is_superadmin=bool(getattr(request.user, "is_superuser", False)),
        force_override=False,
        persist=True,
    )
    SchoolProvisioningEvent.log_event(
        school=school,
        event_type=SchoolProvisioningEvent.EventType.REQUEST_RECEIVED,
        status=SchoolProvisioningEvent.Status.INFO,
        message="Provisioning request accepted.",
        payload={
            "country_code": country_code or (default_region.code if default_region else ""),
            "sub_system": sub_system,
            "education_profile_code": explicit_profile.code if explicit_profile else "",
            "custom_domain": custom_domain or "",
        },
        created_by=request.user if getattr(request, "user", None) and request.user.is_authenticated else None,
    )
    if custom_domain:
        SchoolProvisioningEvent.log_event(
            school=school,
            event_type=SchoolProvisioningEvent.EventType.DOMAIN_PENDING,
            status=SchoolProvisioningEvent.Status.INFO,
            message=f"Custom domain {custom_domain} pending DNS verification.",
            payload={"hostname": custom_domain},
            created_by=request.user if getattr(request, "user", None) and request.user.is_authenticated else None,
        )

    # Enqueue provisioning task (Celery or sync for now)
    try:
        from apps.schools.tasks import provision_school_task
        result = provision_school_task.delay(str(school.id), contact_email=contact_email)
        job_id = getattr(result, "id", None)
        SchoolProvisioningEvent.log_event(
            school=school,
            event_type=SchoolProvisioningEvent.EventType.QUEUED,
            status=SchoolProvisioningEvent.Status.INFO,
            message="Provisioning queued.",
            payload={"job_id": job_id or ""},
            created_by=request.user if getattr(request, "user", None) and request.user.is_authenticated else None,
        )
    except Exception:
        # Run synchronously if Celery not available
        from apps.schools.tasks import provision_school_sync
        SchoolProvisioningEvent.log_event(
            school=school,
            event_type=SchoolProvisioningEvent.EventType.QUEUED,
            status=SchoolProvisioningEvent.Status.WARNING,
            message="Celery unavailable; provisioning started in synchronous fallback mode.",
            payload={},
            created_by=request.user if getattr(request, "user", None) and request.user.is_authenticated else None,
        )
        provision_school_sync(str(school.id), contact_email=contact_email)
        job_id = None

    return JsonResponse(
        {
            "school_id": str(school.id),
            "job_id": job_id,
            "message": "School created; provisioning started.",
            "timeline_url": _safe_school_timeline_url(school.id),
        },
        status=202,
    )


# ---------- Phase G: Emergency Sync Repair (Super Admin) ----------

def _sync_repair_force_overwrite_conflict(conflict, resolved_by):
    """Apply client_data to entity and mark conflict RESOLVED_CLIENT. Call inside transaction.atomic()."""
    from django.utils import timezone
    from apps.api.sync_services import _get_entity_config
    conflict.resolved_by = resolved_by
    conflict.resolved_at = timezone.now()
    conflict.status = "RESOLVED_CLIENT"
    config = _get_entity_config()
    if conflict.entity_type in config:
        model, allowed = config[conflict.entity_type]
        updates = {k: v for k, v in (conflict.client_data or {}).items() if k in allowed}
        if updates:
            try:
                instance = model.objects.get(pk=conflict.entity_id)
                for key, value in updates.items():
                    setattr(instance, key, value)
                update_fields = list(updates.keys())
                if hasattr(instance, "updated_at"):
                    update_fields.append("updated_at")
                instance.save(update_fields=update_fields)
            except model.DoesNotExist:
                pass
    conflict.save(update_fields=["status", "resolved_at", "resolved_by"])


@require_http_methods(["GET", "POST"])
def sync_repair(request, school_id):
    """
    Phase G: Super Admin Emergency Sync Repair. List SyncConflict for a school;
    side-by-side client vs server; Force Overwrite applies client_data with transaction.atomic().
    """
    from django.db import transaction
    from django.shortcuts import redirect
    from django.contrib import messages
    from apps.siteconfig.models import SyncConflict

    school = get_object_or_404(School, pk=school_id)
    if not (getattr(request.user, "is_superuser", False)):
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden("Superuser required for Sync Repair.")

    if request.method == "POST":
        conflict_id = request.POST.get("conflict_id")
        if conflict_id:
            try:
                conflict = SyncConflict.objects.get(pk=int(conflict_id), school_id=school_id, status=SyncConflict.Status.PENDING)
            except (ValueError, SyncConflict.DoesNotExist):
                messages.error(request, "Conflict not found or already resolved.")
            else:
                with transaction.atomic():
                    _sync_repair_force_overwrite_conflict(conflict, request.user)
                messages.success(request, f"Conflict #{conflict_id} resolved (client version applied).")
            return redirect("super:sync_repair", school_id=school_id)

    conflicts = list(
        SyncConflict.objects.filter(school_id=school_id)
        .select_related("reported_by")
        .order_by("-created_at")[:100]
    )
    return render(
        request,
        "schools/super_sync_repair.html",
        {"school": school, "conflicts": conflicts, "dashboard_url": reverse("super:dashboard")},
    )
