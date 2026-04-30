"""
Self-service school signup: public form → create school (is_active=False) →
email verification → activate and provision. No super-admin required.

W1-2: POST /api/trial/ or /start-trial — self-service trial (minimal name, email, country).
"""

from datetime import timedelta
import json
import uuid

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
from apps.schools.marketing_settings_helpers import derive_marketing_demo_tenant_url
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
    """Generate a URL-safe slug from the school name."""
    import re

    s = (name or "").strip().lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    s = s.strip("-")
    return s[:120] or "school"


def _resolved_marketing_demo_tenant_url() -> str:
    """
    URL for 'Return to demo' on signup when ref=demo.
    Uses settings (explicit or TENANT_EXAMPLE_SLUG + base), then the common
    ensure_demo_environment default slug ``demo-school`` when a tenant base domain exists.
    """
    direct = (getattr(settings, "MARKETING_DEMO_TENANT_URL", "") or "").strip()
    if direct:
        return direct
    base = (getattr(settings, "MULTI_TENANT_BASE_DOMAIN", "") or "").strip().lower()
    slug = getattr(settings, "TENANT_EXAMPLE_SLUG", None)
    url = derive_marketing_demo_tenant_url("", slug, base)
    if url:
        return url
    return derive_marketing_demo_tenant_url("", "demo-school", base)


@require_http_methods(["GET", "POST"])
def signup_school(request: HttpRequest):
    """
    Public form: school name, subdomain/slug, admin email, country (optional).
    POST: validate, create School (is_active=False), create SignupVerification,
    send email with verification link, return success or errors.
    """
    if request.method == "GET":
        cc = (request.GET.get("country_code") or "").strip()[:2].upper()
        if not cc:
            cc = (request.session.get("onboarding_country_code") or "").strip()[:2].upper()
        tp = (request.GET.get("term_preset") or "").strip()[:8].upper()
        if tp not in ("", "UK"):
            tp = ""
        name = (request.GET.get("name") or request.GET.get("school_name") or "").strip()[
            :200
        ]
        email = (request.GET.get("email") or "").strip()[:254]
        slug = (request.GET.get("slug") or "").strip()[:120]
        ref = (request.GET.get("ref") or "").strip()[:32]
        return render(
            request,
            "schools/signup_school.html",
            {
                "country_code": cc,
                "term_preset": tp,
                "signup_region_hint": (request.GET.get("region") or "").strip()[:64],
                "curriculum_hint": (request.GET.get("curriculum") or "").strip()[:128],
                "onboarding_prefill_hint": bool(
                    request.session.get("onboarding_correlation_id")
                ),
                "name": name,
                "email": email,
                "slug": slug,
                "signup_ref": ref,
                "marketing_demo_tenant_url": _resolved_marketing_demo_tenant_url(),
            },
        )

    name = (request.POST.get("name") or "").strip()
    slug = (request.POST.get("slug") or "").strip() or _slug_from_name(name)
    email = (request.POST.get("email") or "").strip()
    country_code = (request.POST.get("country_code") or "").strip()[:2].upper()
    term_preset = (
        request.POST.get("term_preset") or ""
    ).strip()  # e.g. "UK" for British terms at signup
    signup_ref = (request.POST.get("signup_ref") or "").strip()[:32]

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
                "signup_ref": signup_ref,
                "marketing_demo_tenant_url": _resolved_marketing_demo_tenant_url(),
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
                "signup_ref": signup_ref,
                "marketing_demo_tenant_url": _resolved_marketing_demo_tenant_url(),
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
    ob_cid = (request.session.get("onboarding_correlation_id") or "").strip()
    if ob_cid or request.session.get("onboarding_plan_slug"):
        rmc_ob = {
            "correlation_id": ob_cid or None,
            "plan_slug": (request.session.get("onboarding_plan_slug") or "").strip()
            or None,
            "template_slug": (request.session.get("onboarding_template_slug") or "").strip()
            or None,
            "school_flavor": (request.session.get("onboarding_school_flavor") or "").strip()
            or None,
            "trial": bool(request.session.get("onboarding_trial", False)),
            "first_value_action_required": True,
        }
        if request.session.get("onboarding_import_site_name"):
            rmc_ob["brand_import"] = {
                "site_name": request.session.get("onboarding_import_site_name"),
                "primary_color": request.session.get("onboarding_import_primary_color"),
                "logo_url": request.session.get("onboarding_import_logo_url"),
            }
        school_settings["rmc_public_onboarding"] = rmc_ob
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

    for key in (
        "onboarding_correlation_id",
        "onboarding_country_code",
        "onboarding_school_flavor",
        "onboarding_plan_slug",
        "onboarding_trial",
        "onboarding_template_slug",
        "onboarding_import_primary_color",
        "onboarding_import_logo_url",
        "onboarding_import_site_name",
        "onboarding_step",
        "_onboarding_start_logged",
        "_onboarding_complete_logged",
    ):
        request.session.pop(key, None)
    request.session.modified = True

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


def _ensure_onboarding_correlation(session) -> str:
    cid = session.get("onboarding_correlation_id")
    if not cid:
        cid = str(uuid.uuid4())
        session["onboarding_correlation_id"] = cid
        session.modified = True
    return str(cid)


def _default_plan_slug(plans, _country_code: str) -> str | None:
    # _country_code reserved for future regional catalog rules (PPP / locale).
    if not plans:
        return None
    best_slug = None
    best_rank = None
    for p in plans:
        slug = (getattr(p, "slug", None) or "").strip()
        if not slug:
            continue
        sl = slug.lower()
        name = (getattr(p, "name", None) or "").lower()
        price = getattr(p, "base_price", None)
        try:
            rank = float(price) if price is not None else 1_000_000.0
        except (TypeError, ValueError):
            rank = 1_000_000.0
        for token in ("trial", "starter", "basic", "standard", "essential"):
            if token in sl or token in name:
                rank -= 500.0
                break
        if best_rank is None or rank < best_rank:
            best_rank = rank
            best_slug = slug
    return best_slug


def _default_template_slug(templates) -> str | None:
    if not templates:
        return None
    for t in templates:
        if getattr(t, "is_default", False):
            return getattr(t, "slug", None) or None
    return getattr(templates[0], "slug", None) or None


def _apply_onboarding_region_defaults(session, plans, templates, country_code: str) -> None:
    if not session.get("onboarding_plan_slug"):
        ps = _default_plan_slug(plans, country_code)
        if ps:
            session["onboarding_plan_slug"] = ps
    if not session.get("onboarding_template_slug"):
        ts = _default_template_slug(templates)
        if ts:
            session["onboarding_template_slug"] = ts


def _maybe_emit_onboarding_start(request, session) -> None:
    if session.get("_onboarding_start_logged"):
        return
    try:
        from apps.schools.funnel_events import record_marketing_funnel_event

        record_marketing_funnel_event(
            "onboarding_start",
            request,
            metadata={
                "correlation_id": session.get("onboarding_correlation_id"),
                "source": "public_onboard_wizard",
            },
        )
    except (ImportError, AttributeError, TypeError, ValueError):
        pass
    session["_onboarding_start_logged"] = True
    session.modified = True


def _maybe_emit_onboarding_complete(request, session) -> None:
    if session.get("_onboarding_complete_logged"):
        return
    try:
        from apps.schools.funnel_events import record_marketing_funnel_event

        record_marketing_funnel_event(
            "onboarding_complete",
            request,
            metadata={
                "correlation_id": session.get("onboarding_correlation_id"),
                "country": session.get("onboarding_country_code"),
                "plan_slug": session.get("onboarding_plan_slug"),
                "template_slug": session.get("onboarding_template_slug"),
                "trial": bool(session.get("onboarding_trial", False)),
            },
        )
    except (ImportError, AttributeError, TypeError, ValueError):
        pass
    session["_onboarding_complete_logged"] = True
    session.modified = True


@require_http_methods(["GET", "POST"])
def onboarding_wizard(request: HttpRequest):
    """
    Public onboarding at /onboard/. Three steps: (1) Region + school type,
    (2) Plan + look (templates, trial, optional brand import),
    (3) Review → signup. Session carries prefs into signup_school (rmc_public_onboarding).
    """
    session = request.session
    _ensure_onboarding_correlation(session)

    step_raw = (
        request.GET.get("step")
        or request.POST.get("step")
        or str(session.get("onboarding_step", 1))
    )
    try:
        step = max(1, min(3, int(step_raw)))
    except (TypeError, ValueError):
        step = 1

    plans = _get_plans_for_onboarding()
    templates = _get_templates_for_onboarding()

    if request.method == "POST":
        if step == 1:
            session["onboarding_country_code"] = (
                (request.POST.get("country_code") or "").strip()[:2].upper()
            )
            session["onboarding_school_flavor"] = (
                request.POST.get("school_flavor") or "general"
            ).strip()
            _apply_onboarding_region_defaults(
                session,
                plans,
                templates,
                session.get("onboarding_country_code") or "",
            )
            session["onboarding_step"] = 2
            session.modified = True
            return redirect(reverse("onboard_wizard") + "?step=2")
        if step == 2:
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
                return redirect(reverse("onboard_wizard") + "?step=2")
            session["onboarding_plan_slug"] = (
                request.POST.get("plan_slug") or ""
            ).strip() or None
            session["onboarding_trial"] = request.POST.get("trial") in (
                "1",
                "true",
                "on",
            )
            session["onboarding_template_slug"] = (
                request.POST.get("template_slug") or ""
            ).strip() or None
            session["onboarding_step"] = 3
            session.modified = True
            return redirect(reverse("onboard_wizard") + "?step=3")

    if session.get("onboarding_country_code"):
        _apply_onboarding_region_defaults(
            session,
            plans,
            templates,
            session.get("onboarding_country_code") or "",
        )

    _maybe_emit_onboarding_start(request, session)
    if step == 3 and session.get("onboarding_country_code"):
        _maybe_emit_onboarding_complete(request, session)

    countries = GlobalGeoCatalog.list_countries()
    default_country = (
        GlobalGeoCatalog.normalize_country_code(request.GET.get("country_code"))
        or session.get("onboarding_country_code")
        or "USA"
    )

    signup_url = reverse("signup_school")
    cid = session.get("onboarding_correlation_id")
    if cid:
        signup_url += f"?ob={str(cid)[:12]}"

    return render(
        request,
        "schools/onboard_wizard.html",
        {
            "step": step,
            "trial_endpoint": reverse("api_trial_school"),
            "signup_url": signup_url,
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
            "onboarding_correlation_id": session.get("onboarding_correlation_id"),
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
        from apps.schools.funnel_events import (
            record_marketing_funnel_event,
            record_school_funnel_once,
        )

        record_school_funnel_once("signup_completed", school, request)
        record_marketing_funnel_event("activation", request, school=school)
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
