"""
Self-service school signup: public form → create school (is_active=False) →
email verification → activate and provision. No super-admin required.

W1-2: POST /api/trial/ or /start-trial — self-service trial (minimal name, email, country).
"""
from datetime import timedelta
import json

from django.conf import settings
from django.contrib import messages
from django.core.mail import send_mail
from django.http import HttpRequest, HttpResponse, HttpResponseBadRequest, JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_http_methods, require_POST
from django.views.decorators.csrf import csrf_exempt

from apps.schools.models import School, SignupVerification
from apps.siteconfig.global_catalog import GlobalGeoCatalog


def _slug_from_name(name: str) -> str:
    """Generate a URL-safe slug from school name."""
    import re
    s = (name or "").strip().lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    s = s.strip("-")
    return s[:120] or "school"


@require_http_methods(["GET", "POST"])
def signup_school(request: HttpRequest):
    """
    Public form: school name, subdomain/slug, admin email, country (optional).
    POST: validate, create School (is_active=False), create SignupVerification,
    send email with verification link, return success or errors.
    """
    if request.method == "GET":
        return render(request, "schools/signup_school.html", {})

    name = (request.POST.get("name") or "").strip()
    slug = (request.POST.get("slug") or "").strip() or _slug_from_name(name)
    email = (request.POST.get("email") or "").strip()
    country_code = (request.POST.get("country_code") or "").strip()[:2].upper()
    term_preset = (request.POST.get("term_preset") or "").strip()  # e.g. "UK" for British terms at signup

    errors = []
    if not name:
        errors.append("School name is required.")
    if not email:
        errors.append("Admin email is required.")
    else:
        try:
            from django.core.validators import validate_email
            validate_email(email)
        except Exception:
            errors.append("Enter a valid email address.")

    if errors:
        if request.headers.get("Accept", "").find("application/json") >= 0:
            return JsonResponse({"ok": False, "errors": errors}, status=400)
        for e in errors:
            messages.error(request, e)
        return render(request, "schools/signup_school.html", {"name": name, "slug": slug, "email": email, "country_code": country_code})

    slug = slug or _slug_from_name(name)
    if School.objects.filter(slug=slug).exists() or School.objects.filter(subdomain=slug).exists():
        errors.append("This school URL is already taken. Choose another.")
        if request.headers.get("Accept", "").find("application/json") >= 0:
            return JsonResponse({"ok": False, "errors": errors}, status=400)
        messages.error(request, errors[0])
        return render(request, "schools/signup_school.html", {"name": name, "slug": slug, "email": email, "country_code": country_code})

    from django.utils.text import slugify
    slug = slugify(slug) or "school"
    if not slug:
        slug = "school"
    subdomain = slug[:120]

    school_settings = {}
    if term_preset and term_preset.upper() in ("UK", "GB"):
        school_settings["term_preset"] = "UK"
    school = School.objects.create(
        name=name,
        slug=slug,
        subdomain=subdomain,
        is_active=False,
        is_approved=True,
        country_code=country_code,
        timezone=getattr(settings, "DEFAULT_SCHOOL_TIMEZONE", "Africa/Douala"),
        settings=school_settings,
    )
    from datetime import timedelta
    expires_at = timezone.now() + timedelta(days=2)
    verification = SignupVerification.objects.create(
        school=school,
        email=email,
        expires_at=expires_at,
    )
    try:
        from apps.schools.funnel_events import record_marketing_funnel_event
        record_marketing_funnel_event("signup", request)
    except Exception:
        pass

    base = request.build_absolute_uri("/").rstrip("/")
    verify_url = f"{base}/verify-signup/?token={verification.token}"

    subject = f"Verify your school: {name}"
    body = (
        f"Hello,\n\n"
        f"You requested to create a school on RunMyCampus: {name}.\n\n"
        f"Click the link below to verify your email and activate your school (link valid for 2 days):\n\n"
        f"{verify_url}\n\n"
        f"If you did not request this, you can ignore this email.\n"
    )
    try:
        send_mail(
            subject=subject,
            message=body,
            from_email=settings.DEFAULT_FROM_EMAIL or "noreply@runmycampus.com",
            recipient_list=[email],
            fail_silently=True,
        )
    except Exception:
        pass

    if request.headers.get("Accept", "").find("application/json") >= 0:
        return JsonResponse({
            "ok": True,
            "school_id": str(school.id),
            "message": "Check your email to verify and activate your school.",
        }, status=201)
    messages.success(request, "Check your email to verify and activate your school.")
    return render(request, "schools/signup_school_done.html", {"email": email})


@require_GET
def onboarding_wizard(request: HttpRequest):
    """
    Public onboarding shell at /onboard/.
    Keeps provisioning entry-point stable while trial API and signup flow evolve.
    """
    return render(
        request,
        "schools/onboard_wizard.html",
        {
            "trial_endpoint": reverse("api_trial_school"),
            "signup_url": reverse("signup_school"),
        },
    )


@require_GET
def verify_signup(request: HttpRequest):
    """
    GET ?token=xxx: look up SignupVerification, if valid set school.is_active=True,
    run provisioning, mark verification used, redirect to login.
    """
    token_str = (request.GET.get("token") or "").strip()
    if not token_str:
        return render(request, "schools/verify_signup.html", {"error": "Missing verification token."}, status=400)

    try:
        import uuid
        token_uuid = uuid.UUID(token_str)
    except (ValueError, TypeError):
        return render(request, "schools/verify_signup.html", {"error": "Invalid token."}, status=400)

    verification = SignupVerification.objects.filter(
        token=token_uuid,
        verified_at__isnull=True,
        expires_at__gt=timezone.now(),
    ).select_related("school").first()

    if not verification:
        return render(request, "schools/verify_signup.html", {"error": "Link expired or already used."}, status=400)

    school = verification.school
    school.is_active = True
    school.save(update_fields=["is_active", "updated_at"])
    verification.verified_at = timezone.now()
    verification.save(update_fields=["verified_at"])
    try:
        from apps.schools.funnel_events import record_marketing_funnel_event
        record_marketing_funnel_event("activation", request)
    except Exception:
        pass

    try:
        from apps.schools.tasks import provision_school_sync
        provision_school_sync(str(school.id), contact_email=verification.email)
    except Exception:
        pass

    login_url = (settings.LOGIN_URL or "/authentication/login/").lstrip("/")
    # Optional: send new school admin to backend dashboard after first login
    try:
        from django.urls import reverse
        next_path = reverse("accounts:backend_dashboard")
    except Exception:
        next_path = "/"
    return redirect(f"/{login_url}?next={next_path}")


@require_POST
@csrf_exempt
def api_trial_school(request: HttpRequest):
    """
    W1-2: Self-service trial API. POST JSON: name, contact_email, country_code (optional).
    Creates school with billing_type=FREE_TRIAL, trial_end_date=now+14d, enqueues provisioning.
    Returns 202 with school_id, job_id, message "We'll email when ready".
    """
    try:
        data = json.loads(request.body) if request.body else {}
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    name = (data.get("name") or "").strip()
    contact_email = (data.get("contact_email") or "").strip()
    country_code = (data.get("country_code") or "").strip()[:2].upper()
    region_code = GlobalGeoCatalog.normalize_country_code(country_code)

    errors = []
    if not name:
        errors.append("name is required")
    if not contact_email:
        errors.append("contact_email is required")
    if errors:
        return JsonResponse({"errors": errors}, status=400)

    try:
        from django.core.validators import validate_email
        validate_email(contact_email)
    except Exception:
        errors.append("Enter a valid email address.")
        return JsonResponse({"errors": errors}, status=400)

    slug = _slug_from_name(name)
    if School.objects.filter(slug=slug).exists() or School.objects.filter(subdomain=slug).exists():
        return JsonResponse({"errors": ["This school URL is already taken. Choose another name."]}, status=400)

    subdomain = slug[:120]
    default_region = None
    if country_code:
        from apps.siteconfig.education_profile_engine import ensure_region_for_country
        from apps.siteconfig.models import RegionConfig
        default_region = RegionConfig.objects.filter(code=region_code).first()
        if not default_region:
            default_region = ensure_region_for_country(region_code or country_code, timezone_hint="UTC")

    trial_end = (timezone.now() + timedelta(days=14)).date()
    school = School.objects.create(
        name=name,
        slug=slug,
        subdomain=subdomain,
        is_active=False,
        is_approved=True,
        billing_type=School.BillingType.FREE_TRIAL,
        trial_end_date=trial_end,
        default_region=default_region,
        country_code=country_code,
        timezone=getattr(settings, "DEFAULT_SCHOOL_TIMEZONE", "Africa/Douala"),
    )
    if default_region:
        school.settings = (school.settings or {})
        school.settings["country_code"] = country_code
        school.save(update_fields=["settings"])
        try:
            from apps.policies.policy_registry import invalidate_policy_cache
            invalidate_policy_cache(school)
        except Exception:
            pass

    from apps.schools.tasks import provision_school_task, provision_school_sync
    from apps.schools.models import SchoolProvisioningEvent

    SchoolProvisioningEvent.log_event(
        school=school,
        event_type=SchoolProvisioningEvent.EventType.REQUEST_RECEIVED,
        status=SchoolProvisioningEvent.Status.INFO,
        message="Trial signup received.",
        payload={"contact_email": contact_email, "country_code": country_code or ""},
        created_by=request.user if getattr(request, "user", None) and request.user.is_authenticated else None,
    )
    job_id = None
    try:
        result = provision_school_task.delay(str(school.id), contact_email=contact_email)
        job_id = getattr(result, "id", None)
        SchoolProvisioningEvent.log_event(
            school=school,
            event_type=SchoolProvisioningEvent.EventType.QUEUED,
            status=SchoolProvisioningEvent.Status.INFO,
            message="Provisioning queued.",
            payload={"job_id": job_id or ""},
            created_by=None,
        )
    except Exception:
        provision_school_sync(str(school.id), contact_email=contact_email)
        SchoolProvisioningEvent.log_event(
            school=school,
            event_type=SchoolProvisioningEvent.EventType.QUEUED,
            status=SchoolProvisioningEvent.Status.WARNING,
            message="Celery unavailable; provisioning ran synchronously.",
            payload={},
            created_by=None,
        )

    try:
        timeline_url = request.build_absolute_uri(
            reverse("super:api_school_timeline", args=[school.id])
        )
    except Exception:
        timeline_url = ""

    return JsonResponse(
        {
            "school_id": str(school.id),
            "job_id": job_id,
            "message": "We'll email when ready.",
            "timeline_url": timeline_url,
        },
        status=202,
    )
