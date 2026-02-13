"""
Super Admin views: dashboard (list schools) and Create School wizard.
Access restricted to SUPERADMIN or is_superuser via TenantSuperAdminRequiredMiddleware.
"""
from django.contrib import messages
from django.db.models import Count
from django.shortcuts import render, redirect
from django.views.decorators.http import require_http_methods, require_POST
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.csrf import csrf_protect
from django.http import JsonResponse

from .models import School, SchoolMembership


def super_dashboard(request):
    """List all schools with basic stats (student/teacher counts for usage/billing)."""
    schools = (
        School.objects.all()
        .order_by("name")
        .annotate(member_count=Count("memberships"))
        .annotate(student_count=Count("student_profiles", distinct=True))
        .annotate(teacher_count=Count("teacher_profiles", distinct=True))
    )
    return render(
        request,
        "schools/super_dashboard.html",
        {"schools": schools},
    )


@require_http_methods(["GET", "POST"])
def create_school_wizard(request):
    """Multi-step wizard: Step 1 identity, Step 2 region, Step 3 branding. POST submits to API."""
    from apps.siteconfig.models import RegionConfig

    if request.method == "POST":
        # Wizard form submitted via JS to api_create_school; this is fallback or redirect
        return redirect("super:api_create_school")

    regions = RegionConfig.objects.all().order_by("name")
    return render(
        request,
        "schools/super_create_school_wizard.html",
        {"regions": regions},
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

    from apps.siteconfig.models import RegionConfig
    default_region = None
    if region_code:
        default_region = RegionConfig.objects.filter(code=region_code).first()

    school = School.objects.create(
        name=name,
        slug=slug,
        subdomain=subdomain or slug,
        sub_system=sub_system,
        default_region=default_region,
        primary_color=primary_color,
        accent_color=accent_color,
        custom_domain=custom_domain or "",
        is_active=False,
        settings={
            "contact_email": contact_email,
            "provisioning": {"logo_uploaded": False},
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
