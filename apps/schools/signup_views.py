"""
Self-service school signup: public form → create school (is_active=False) →
email verification → activate and provision. No super-admin required.

W1-2: POST /api/trial/ or /start-trial — self-service trial (minimal name, email, country).
"""

from datetime import timedelta
import json

from django.conf import settings
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.mail import send_mail
from django.http import HttpRequest, JsonResponse
from django.shortcuts import redirect, render
from django.urls import NoReverseMatch, reverse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_http_methods, require_POST
from django.views.decorators.cache import never_cache

from apps.platform_runtime.helpers import get_platform_defaults
from apps.schools.models import School, SignupVerification
from apps.siteconfig.global_catalog import GlobalGeoCatalog

try:
    from django_ratelimit.decorators import ratelimit
except ImportError:

    def ratelimit(*args, **kwargs):
        def dec(f):
            return f

        return dec


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
    term_preset = (
        request.POST.get("term_preset") or ""
    ).strip()  # e.g. "UK" for British terms at signup

    errors = []
    if not name:
        errors.append("School name is required.")
    if not email:
        errors.append("Admin email is required.")
    else:
        try:
            from django.core.validators import validate_email

            validate_email(email)
        except ValidationError:
            errors.append("Enter a valid email address.")

    if errors:
        if request.headers.get("Accept", "").find("application/json") >= 0:
            return JsonResponse({"ok": False, "errors": errors}, status=400)
        for e in errors:
            messages.error(request, e)
        return render(
            request,
            "schools/signup_school.html",
            {
                "name": name,
                "slug": slug,
                "email": email,
                "country_code": country_code,
                "term_preset": term_preset,
            },
        )

    slug = slug or _slug_from_name(name)
    if (
        School.objects.filter(slug=slug).exists()
        or School.objects.filter(subdomain=slug).exists()
    ):
        errors.append("This school URL is already taken. Choose another.")
        if request.headers.get("Accept", "").find("application/json") >= 0:
            return JsonResponse({"ok": False, "errors": errors}, status=400)
        messages.error(request, errors[0])
        return render(
            request,
            "schools/signup_school.html",
            {
                "name": name,
                "slug": slug,
                "email": email,
                "country_code": country_code,
                "term_preset": term_preset,
            },
        )

    from django.utils.text import slugify

    slug = slugify(slug) or "school"
    if not slug:
        slug = "school"
    subdomain = slug[:120]

    school_settings = {}
    if term_preset and term_preset.upper() in ("UK", "GB"):
        school_settings["term_preset"] = "UK"
    country_defaults = GlobalGeoCatalog.country_defaults(country_code)
    school = School.objects.create(
        name=name,
        slug=slug,
        subdomain=subdomain,
        is_active=False,
        is_approved=True,
        country_code=country_code,
        timezone=str(
            country_defaults.get("timezone")
            or getattr(settings, "DEFAULT_SCHOOL_TIMEZONE", "UTC")
        ),
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
    except (ImportError, AttributeError, TypeError, ValueError):
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
    except (OSError, ConnectionError, ValueError, TypeError):
        pass

    if request.headers.get("Accept", "").find("application/json") >= 0:
        return JsonResponse(
            {
                "ok": True,
                "school_id": str(school.id),
                "message": "Check your email to verify and activate your school.",
            },
            status=201,
        )
    messages.success(request, "Check your email to verify and activate your school.")
    return render(request, "schools/signup_school_done.html", {"email": email})


def _get_plans_for_onboarding():
    """Return active plans for public onboarding (platform/public schema). Empty list if unavailable."""
    try:
        from apps.plans_entitlements.models import Plan

        return list(Plan.objects.filter(is_active=True).order_by("name")[:20])
    except (ImportError, AttributeError, TypeError, ValueError):
        return []


def _get_templates_for_onboarding():
    """Return active theme packs as templates for public onboarding. Empty list if unavailable."""
    try:
        from apps.brand_experience.models import ThemePack

        return list(
            ThemePack.objects.filter(is_active=True).order_by("-is_default", "name")[
                :30
            ]
        )
    except (ImportError, AttributeError, TypeError, ValueError):
        return []


@require_http_methods(["GET", "POST"])
def onboarding_wizard(request: HttpRequest):
    """
    Public onboarding at /onboard/. Multi-step guided flow: (1) Welcome+region, (2) Plan, (3) Branding+template, (4) Done.
    Session holds: onboarding_step, country_code, school_flavor, plan_slug, template_slug.
    """
    session = request.session
    step = (
        request.GET.get("step")
        or request.POST.get("step")
        or str(session.get("onboarding_step", 1))
    )
    try:
        step = max(1, min(4, int(step)))
    except (TypeError, ValueError):
        step = 1

    if request.method == "POST":
        if step == 1:
            session["onboarding_country_code"] = (
                (request.POST.get("country_code") or "").strip()[:2].upper()
            )
            session["onboarding_school_flavor"] = (
                request.POST.get("school_flavor") or "general"
            ).strip()
            session["onboarding_step"] = 2
            session.modified = True
            return redirect(reverse("onboard_wizard") + "?step=2")
        if step == 2:
            session["onboarding_plan_slug"] = (
                request.POST.get("plan_slug") or ""
            ).strip() or None
            session["onboarding_trial"] = request.POST.get("trial") in (
                "1",
                "true",
                "on",
            )
            session["onboarding_step"] = 3
            session.modified = True
            return redirect(reverse("onboard_wizard") + "?step=3")
        if step == 3:
            if request.POST.get("brand_import") == "1":
                url = (request.POST.get("import_url") or "").strip()
                if url and request.POST.get("consent") in ("1", "true", "on"):
                    from apps.siteconfig.brand_import import fetch_and_parse_brand_url

                    result = fetch_and_parse_brand_url(url)
                    if not result.get("error"):
                        session["onboarding_import_primary_color"] = result.get(
                            "primary_color"
                        )
                        session["onboarding_import_logo_url"] = result.get("logo_url")
                        session["onboarding_import_site_name"] = result.get("site_name")
                        session.modified = True
                return redirect(reverse("onboard_wizard") + "?step=3")
            session["onboarding_template_slug"] = (
                request.POST.get("template_slug") or ""
            ).strip() or None
            session["onboarding_step"] = 4
            session.modified = True
            return redirect(reverse("onboard_wizard") + "?step=4")
        if step == 4:
            session.pop("onboarding_step", None)
            session.pop("onboarding_country_code", None)
            session.pop("onboarding_school_flavor", None)
            session.pop("onboarding_plan_slug", None)
            session.pop("onboarding_trial", None)
            session.pop("onboarding_template_slug", None)
            session.modified = True
            return redirect(reverse("signup_school"))

    countries = GlobalGeoCatalog.list_countries()
    default_country = (
        GlobalGeoCatalog.normalize_country_code(request.GET.get("country_code"))
        or session.get("onboarding_country_code")
        or "USA"
    )
    plans = _get_plans_for_onboarding()
    templates = _get_templates_for_onboarding()

    return render(
        request,
        "schools/onboard_wizard.html",
        {
            "step": step,
            "trial_endpoint": reverse("api_trial_school"),
            "signup_url": reverse("signup_school"),
            "countries": countries[:120],
            "default_country_code": default_country,
            "plans": plans,
            "templates": templates,
            "onboarding_country_code": session.get("onboarding_country_code"),
            "onboarding_school_flavor": session.get(
                "onboarding_school_flavor", "general"
            ),
            "onboarding_plan_slug": session.get("onboarding_plan_slug"),
            "onboarding_trial": session.get("onboarding_trial", False),
            "onboarding_template_slug": session.get("onboarding_template_slug"),
            "website_import_doc_url": "#",
            "onboarding_import_primary_color": session.get(
                "onboarding_import_primary_color"
            ),
            "onboarding_import_logo_url": session.get("onboarding_import_logo_url"),
            "onboarding_import_site_name": session.get("onboarding_import_site_name"),
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
        return render(
            request,
            "schools/verify_signup.html",
            {"error": "Missing verification token."},
            status=400,
        )

    try:
        import uuid

        token_uuid = uuid.UUID(token_str)
    except (ValueError, TypeError):
        return render(
            request,
            "schools/verify_signup.html",
            {"error": "Invalid token."},
            status=400,
        )

    verification = (
        SignupVerification.objects.filter(
            token=token_uuid,
            verified_at__isnull=True,
            expires_at__gt=timezone.now(),
        )
        .select_related("school")
        .first()
    )

    if not verification:
        return render(
            request,
            "schools/verify_signup.html",
            {"error": "Link expired or already used."},
            status=400,
        )

    school = verification.school
    school.is_active = True
    school.save(update_fields=["is_active", "updated_at"])
    verification.verified_at = timezone.now()
    verification.save(update_fields=["verified_at"])
    try:
        from apps.schools.funnel_events import record_marketing_funnel_event

        record_marketing_funnel_event("activation", request)
    except (ImportError, AttributeError, TypeError, ValueError):
        pass

    try:
        from apps.schools.tasks import provision_school_sync

        provision_school_sync(str(school.id), contact_email=verification.email)
    except (ImportError, AttributeError, TypeError, ValueError, OSError):
        pass

    login_url = (settings.LOGIN_URL or "/authentication/login/").lstrip("/")
    # Optional: send new school admin to backend dashboard after first login
    try:
        next_path = reverse("accounts:backend_dashboard")
    except NoReverseMatch:
        next_path = "/"
    return redirect(f"/{login_url}?next={next_path}")


@require_POST
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
    except ValidationError:
        errors.append("Enter a valid email address.")
        return JsonResponse({"errors": errors}, status=400)

    slug = _slug_from_name(name)
    if (
        School.objects.filter(slug=slug).exists()
        or School.objects.filter(subdomain=slug).exists()
    ):
        return JsonResponse(
            {"errors": ["This school URL is already taken. Choose another name."]},
            status=400,
        )

    subdomain = slug[:120]
    default_region = None
    if country_code:
        from apps.siteconfig.education_profile_engine import ensure_region_for_country
        from apps.global_registries.models import RegionConfig

        default_region = RegionConfig.objects.filter(code=region_code).first()
        if not default_region:
            default_region = ensure_region_for_country(
                region_code or country_code, timezone_hint="UTC"
            )

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
        timezone=getattr(settings, "DEFAULT_SCHOOL_TIMEZONE", None)
        or get_platform_defaults(use_db=False)["timezone"],
    )
    if default_region:
        school.settings = school.settings or {}
        school.settings["country_code"] = country_code
        school.save(update_fields=["settings"])
        try:
            from apps.policies.policy_registry import invalidate_policy_cache

            invalidate_policy_cache(school)
        except (ImportError, AttributeError, TypeError, ValueError):
            pass

    from apps.schools.tasks import dispatch_provision_school
    from apps.schools.models import SchoolProvisioningEvent

    SchoolProvisioningEvent.log_event(
        school=school,
        event_type=SchoolProvisioningEvent.EventType.REQUEST_RECEIVED,
        status=SchoolProvisioningEvent.Status.INFO,
        message="Trial signup received.",
        payload={"contact_email": contact_email, "country_code": country_code or ""},
        created_by=request.user
        if getattr(request, "user", None) and request.user.is_authenticated
        else None,
    )
    dispatch = dispatch_provision_school(str(school.id), contact_email=contact_email)
    job_id = dispatch.get("job_id")
    payload = {"job_id": job_id or ""}
    if dispatch.get("fallback") and dispatch.get("reason"):
        payload["fallback_reason"] = dispatch["reason"]
    SchoolProvisioningEvent.log_event(
        school=school,
        event_type=SchoolProvisioningEvent.EventType.QUEUED,
        status=(
            SchoolProvisioningEvent.Status.WARNING
            if dispatch.get("fallback")
            else SchoolProvisioningEvent.Status.INFO
        ),
        message=dispatch.get("message") or "Provisioning queued.",
        payload=payload,
        created_by=None,
    )

    try:
        timeline_url = request.build_absolute_uri(
            reverse("super:api_school_timeline", args=[school.id])
        )
    except NoReverseMatch:
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


@never_cache
@require_POST
@ratelimit(key="ip", rate="10/h", method="POST", block=True)
def brand_import_api(request: HttpRequest):
    """
    Public API: POST with url + consent=1. Fetches URL and returns primary_color, logo_url, site_name.
    Used by onboarding and Theme & Experience. Consent required; rate limited by IP.
    """
    consent = request.POST.get("consent") in ("1", "true", "on")
    if not consent and (request.content_type or "").strip().startswith(
        "application/json"
    ):
        try:
            consent = json.loads(request.body or "{}").get("consent")
        except (json.JSONDecodeError, TypeError, AttributeError):
            pass
    if not consent:
        return JsonResponse(
            {"error": "Consent required to fetch external URL."}, status=400
        )
    url = (request.POST.get("url") or "").strip()
    if not url and request.content_type and "application/json" in request.content_type:
        try:
            data = json.loads(request.body or "{}")
            url = (data.get("url") or "").strip()
        except (json.JSONDecodeError, TypeError, AttributeError):
            pass
    if not url:
        return JsonResponse({"error": "URL is required."}, status=400)
    from apps.siteconfig.brand_import import fetch_and_parse_brand_url

    result = fetch_and_parse_brand_url(url)
    if result.get("error"):
        return JsonResponse({"error": result["error"]}, status=400)
    return JsonResponse(
        {k: v for k, v in result.items() if k != "error" and v is not None}
    )
