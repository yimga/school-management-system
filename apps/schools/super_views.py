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
from .models import School, SchoolProvisioningEvent


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


def super_dashboard(request):
    """List all schools with basic stats (student/teacher counts for usage/billing)."""
    latest_event_query = SchoolProvisioningEvent.objects.filter(school_id=OuterRef("pk")).order_by("-created_at", "-id")
    schools = list(
        School.objects.all()
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
    return render(
        request,
        "schools/super_dashboard.html",
        {"schools": schools},
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
def api_education_profiles(request):
    country_code = GlobalGeoCatalog.normalize_country_code(request.GET.get("country_code"))
    sub_system = (request.GET.get("sub_system") or School.SubSystem.EN).strip().upper()
    valid_subsystems = {School.SubSystem.EN, School.SubSystem.FR, School.SubSystem.INT}
    if sub_system not in valid_subsystems:
        sub_system = School.SubSystem.EN

    profiles = list_profile_options(country_code=country_code, sub_system=sub_system)
    return JsonResponse(
        {
            "country_code": country_code,
            "sub_system": sub_system,
            "profiles": profiles,
            "auto_option": {
                "code": "",
                "name": "Auto by Country and Sub-system",
                "description": "Recommended. Provisioning resolves the best profile automatically.",
            },
        }
    )


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


@require_POST
def api_create_school(request):
    """
    Validate payload, create School row (is_active=False), enqueue provisioning task.
    Returns 202 + job_id or 400 with errors.
    """
    import json

    try:
        data = json.loads(request.body) if request.body else {}
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    name = (data.get("name") or "").strip()
    slug = (data.get("slug") or "").strip().lower().replace(" ", "-")
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
    primary_color = (data.get("primary_color") or "#0d6efd").strip()
    accent_color = (data.get("accent_color") or "#198754").strip()
    custom_domain = (data.get("custom_domain") or "").strip()

    errors = []
    if not name:
        errors.append("name is required")
    if not slug:
        errors.append("slug is required")
    if slug and not subdomain:
        subdomain = slug

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

    school = School.objects.create(
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
        settings={
            "contact_email": contact_email,
            "provisioning": {
                "logo_uploaded": False,
                "education_profile_mode": "explicit" if explicit_profile else "auto",
            },
            "education_profile_code": explicit_profile.code if explicit_profile else "",
            "location": location_payload,
            "custom_domain": {
                "hostname": custom_domain or "",
                "status": "pending_verification" if custom_domain else "not_configured",
                "verified": False,
            },
        },
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
