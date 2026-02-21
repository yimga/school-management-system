"""
Super Admin views: dashboard (list schools) and Create School wizard.
Access restricted to SUPERADMIN or is_superuser via TenantSuperAdminRequiredMiddleware.
"""
from django.contrib import messages
from django.db.models import Count
from django.shortcuts import render, redirect
from django.urls import NoReverseMatch, reverse
from django.views.decorators.http import require_http_methods, require_POST
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.csrf import csrf_protect
from django.http import JsonResponse

from .models import School, SchoolMembership


def _safe_school_admin_change_url(school_id) -> str:
    try:
        return reverse("admin:schools_school_change", args=[school_id])
    except NoReverseMatch:
        return ""
    except Exception:
        return ""


def super_dashboard(request):
    """List all schools with basic stats (student/teacher counts for usage/billing)."""
    schools = list(
        School.objects.all()
        .order_by("name")
        .annotate(member_count=Count("memberships"))
        .annotate(student_count=Count("student_profiles", distinct=True))
        .annotate(teacher_count=Count("teacher_profiles", distinct=True))
    )
    for school in schools:
        school.admin_edit_url = _safe_school_admin_change_url(school.pk)
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
    WeatherLocation.ensure_seed_data()
    locations = list(
        WeatherLocation.objects.select_related("region")
        .filter(is_active=True)
        .order_by("region__name", "sort_order", "city")
    )
    defaults = default_header_weather_config()
    countries = []
    seen = set()
    for loc in locations:
        if loc.region_id in seen:
            continue
        seen.add(loc.region_id)
        countries.append({"code": loc.region_id, "name": loc.region.name})
    cities = [
        {
            "id": loc.pk,
            "country_code": loc.region_id,
            "city": loc.city,
            "label": loc.display_label,
            "timezone": loc.timezone or loc.region.timezone or "UTC",
        }
        for loc in locations
    ]
    return render(
        request,
        "schools/super_create_school_wizard.html",
        {
            "regions": regions,
            "countries": countries,
            "cities": cities,
            "default_country_code": defaults.get("header_weather_country_code", "CMR"),
            "school_admin_edit_template": _safe_school_admin_change_url("00000000-0000-0000-0000-000000000000"),
        },
    )


@require_POST
def api_create_school(request):
    """
    Validate payload, create School row (is_active=False), enqueue provisioning task.
    Returns 202 + job_id or 400 with errors.
    """
    import json
    from django.views.decorators.csrf import csrf_protect
    from django.views.decorators.http import require_POST

    try:
        data = json.loads(request.body) if request.body else {}
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    name = (data.get("name") or "").strip()
    slug = (data.get("slug") or "").strip().lower().replace(" ", "-")
    subdomain = (data.get("subdomain") or slug or "").strip().lower()
    contact_email = (data.get("contact_email") or "").strip()
    region_code = (data.get("region_code") or "").strip()
    country_code = (data.get("country_code") or region_code or "").strip().upper()
    city_id = (data.get("city_id") or "").strip()
    sub_system = (data.get("sub_system") or "EN").strip()
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

    from apps.siteconfig.models import RegionConfig, WeatherLocation
    default_region = None
    selected_location = None
    if city_id:
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
    if selected_location:
        default_region = selected_location.region
        country_code = selected_location.region_id
    if default_region is None and country_code:
        default_region = RegionConfig.objects.filter(code=country_code).first()
    if default_region is None and region_code:
        default_region = RegionConfig.objects.filter(code=region_code).first()
    resolved_timezone = (
        (selected_location.timezone if selected_location else "")
        or (default_region.timezone if default_region else "")
        or "UTC"
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
            "provisioning": {"logo_uploaded": False},
            "location": {
                "country_code": country_code or (default_region.code if default_region else ""),
                "city": selected_location.city if selected_location else "",
                "label": selected_location.display_label if selected_location else "",
                "timezone": resolved_timezone,
            },
        },
    )

    # Enqueue provisioning task (Celery or sync for now)
    try:
        from apps.schools.tasks import provision_school_task
        result = provision_school_task.delay(str(school.id), contact_email=contact_email)
        job_id = getattr(result, "id", None)
    except Exception:
        # Run synchronously if Celery not available
        from apps.schools.tasks import provision_school_sync
        provision_school_sync(str(school.id), contact_email=contact_email)
        job_id = None

    return JsonResponse(
        {"school_id": str(school.id), "job_id": job_id, "message": "School created; provisioning started."},
        status=202,
    )
