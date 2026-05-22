"""
Self-service school signup: public form → create school (is_active=False) →
email verification → activate and provision. No super-admin required.

W1-2: POST /api/trial/ or /start-trial — self-service trial (minimal name, email, country).
"""

from datetime import timedelta
import json
import logging
import time
import uuid

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model, login as auth_login
from django.core.exceptions import ValidationError
from django.core.mail import send_mail  # noqa: F401 — retained for legacy callsites
# v3.57.x Wave 8 Agent C — route signup verification email through the
# canonical reliability-hardened sender (retries + EmailDeliveryEvent
# audit row). ``send_transactional`` mirrors fail_silently semantics:
# it never raises, returns a status dict instead.
from apps.schoolops.email_delivery import send_transactional

logger = logging.getLogger(__name__)
from django.http import HttpRequest, JsonResponse
from django.shortcuts import redirect, render
from django.urls import NoReverseMatch, reverse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_http_methods, require_POST
from django.views.decorators.cache import never_cache

from apps.platform_runtime.helpers import get_platform_defaults
from apps.schools.marketing_settings_helpers import derive_marketing_demo_tenant_url


def _alpha2_to_flag_emoji(alpha2: str) -> str:
    """Convert ISO alpha-2 country code (e.g. ``KE``) to its flag emoji.

    Uses Unicode regional indicator symbols (U+1F1E6 onwards). Returns
    an empty string for inputs that aren't exactly 2 ASCII letters so
    the template silently renders no glyph on bad data rather than
    showing a mojibake fragment.
    """
    value = (alpha2 or "").strip().upper()
    if len(value) != 2 or not value.isascii() or not value.isalpha():
        return ""
    try:
        return "".join(chr(0x1F1E6 + (ord(ch) - ord("A"))) for ch in value)
    except (TypeError, ValueError):
        return ""


def _signup_countries() -> list[dict[str, str]]:
    """
    Country choices for the public signup dropdown.

    v3.58.x Wave 9: routes through ``GlobalGeoCatalog.list_countries()``
    so the dropdown picks up the full pycountry-backed catalog (falling
    back to the ``RegionConfig`` model when optional deps are missing).
    Each row carries:

        iso_alpha2   ISO 3166-1 alpha-2 code (e.g. "KE")
        code         ISO 3166-1 alpha-3 code (e.g. "KEN")
        name         display name
        flag_emoji   derived from alpha-2 (Unicode regional indicators)
        timezone     dominant IANA timezone for the country
        curriculum   curriculum hint (empty by default)

    Capped at 120 rows per spec. Returns an empty list on ANY failure
    (catalog deps unavailable, DB unreachable, etc.) — the signup
    template's free-text input fallback activates in that case.
    """
    try:
        from apps.siteconfig.global_catalog import GlobalGeoCatalog

        rows = GlobalGeoCatalog.list_countries() or []
        out: list[dict[str, str]] = []
        for row in rows[:120]:
            alpha2 = str(row.get("code_alpha2") or "").upper().strip()
            if not alpha2:
                continue
            out.append(
                {
                    "iso_alpha2": alpha2,
                    "code": str(row.get("code") or alpha2),
                    "name": str(row.get("name") or alpha2),
                    "flag_emoji": _alpha2_to_flag_emoji(alpha2),
                    "timezone": str(row.get("timezone") or "UTC"),
                    "curriculum": "",
                }
            )
        return out
    except Exception:
        return []
from apps.schools.models import School, SignupVerification
from apps.schools.onboarding_vendors import (
    DOMAINS_BY_SLUG,
    ONBOARDING_DATA_DOMAINS,
    ONBOARDING_VENDORS,
    estimate_minutes,
    resolve_vendor,
)
from apps.siteconfig.global_catalog import GlobalGeoCatalog

# v3.17 (2026-05-17): public onboarding gained a Migration step.
# Order: 1 Region/type → 2 Plan/look → 3 Migration → 4 Review → signup.
ONBOARDING_TOTAL_STEPS = 4
ONBOARDING_STEP_MIGRATION = 3
ONBOARDING_STEP_REVIEW = 4

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


# Wave L7 (v3.61.8 — 2026-05-22): public signup 2.0.
# - inline migration vendor picker (drives lifecycle.services_migration
#   auto-launch hook by writing settings['migration_intent'] at create time)
# - school-type cards (drives School.primary_sector at create time)
# - Accept-Language → country-code auto-detect when not explicitly passed
# - polished success page wired through with the same intent context

_SCHOOL_TYPE_TO_PRIMARY_SECTOR = {
    "preschool":  "early_childhood",
    "primary":    "primary",
    "k12":        "k12",
    "secondary":  "secondary",
    "college":    "higher_ed",
    "university": "higher_ed",
    "mixed":      "k12",
}

_SIGNUP_VENDOR_SLUGS = {
    "powerschool", "blackbaud", "veracross", "infinite_campus",
    "alma", "facts", "skyward", "managebac", "toddle",
    "oneroster", "csv", "spreadsheet", "other",
}


def _country_from_accept_language(request) -> str:
    """Best-effort country code from Accept-Language header.

    Returns "" when we can't extract a confident 2-letter ISO. Never
    raises — falls through to the existing manual picker.
    """
    try:
        header = (request.META.get("HTTP_ACCEPT_LANGUAGE") or "").strip()
        if not header:
            return ""
        primary = header.split(",")[0].strip()
        if "-" in primary:
            tail = primary.split("-")[-1].strip().upper()[:2]
            if len(tail) == 2 and tail.isalpha():
                return tail
    except Exception:  # noqa: BLE001
        pass
    return ""


@require_http_methods(["GET", "POST"])
def signup_school(request: HttpRequest):
    """
    Public form: school name, subdomain/slug, admin email, country (optional).
    POST: validate, create School (is_active=False), create SignupVerification,
    send email with verification link, return success or errors.

    v3.58.x Wave 9 Agent K — request-lifetime timing instrumentation +
    async verification email send (so a slow / unreachable SMTP can
    never time out the signup HTTP request lifecycle).
    v3.61.8 Wave L7 — vendor + school-type intent capture, Accept-Language
    country fallback, lifecycle.services_migration auto-launch hook.
    """
    t0 = time.monotonic()
    if request.method == "GET":
        cc = (request.GET.get("country_code") or "").strip()[:2].upper()
        if not cc:
            cc = (request.session.get("onboarding_country_code") or "").strip()[:2].upper()
        if not cc:
            cc = _country_from_accept_language(request)
        tp = (request.GET.get("term_preset") or "").strip()[:8].upper()
        if tp not in ("", "UK"):
            tp = ""
        name = (request.GET.get("name") or request.GET.get("school_name") or "").strip()[
            :200
        ]
        email = (request.GET.get("email") or "").strip()[:254]
        slug = (request.GET.get("slug") or "").strip()[:120]
        ref = (request.GET.get("ref") or "").strip()[:32]
        if not request.session.get("rmc_signup_started_event"):
            try:
                from apps.schools.funnel_events import record_marketing_funnel_event

                record_marketing_funnel_event("signup_started", request)
            except ImportError:
                pass
            request.session["rmc_signup_started_event"] = True
            request.session.modified = True
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
                # v3.58.x: ISO alpha-2 country dropdown choices. Template
                # falls back to a free-text input when this list is empty.
                "signup_countries": _signup_countries(),
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
    # Wave L7 — intent capture for downstream auto-launch hooks.
    migration_vendor = (request.POST.get("migration_vendor") or "").strip().lower()
    if migration_vendor and migration_vendor not in _SIGNUP_VENDOR_SLUGS:
        migration_vendor = ""
    school_type = (request.POST.get("school_type") or "").strip().lower()
    if school_type and school_type not in _SCHOOL_TYPE_TO_PRIMARY_SECTOR:
        school_type = ""

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
                "signup_countries": _signup_countries(),
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
                # v3.58.x Wave 9: also pass signup_countries on this
                # POST-error path so the country <select> survives the
                # slug-taken re-render with the operator's selection
                # still highlighted.
                "signup_countries": _signup_countries(),
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
            # Pass 7: carry pack picker + sample-data choice into provisioning.
            "pack_slug": (request.session.get("onboarding_pack_slug") or "").strip()
            or None,
            "sample_data": bool(request.session.get("onboarding_sample_data", False)),
        }
        if request.session.get("onboarding_import_site_name"):
            rmc_ob["brand_import"] = {
                "site_name": request.session.get("onboarding_import_site_name"),
                "primary_color": request.session.get("onboarding_import_primary_color"),
                "logo_url": request.session.get("onboarding_import_logo_url"),
            }
        # v3.17 (2026-05-17): carry the Migration step intent into school.settings
        # so verify_signup can route the new admin to the handoff page after
        # magic-link activation. None means "skip / set up later" — verify_signup
        # falls back to the normal dashboard redirect in that case.
        migrate_vendor = (request.session.get("onboarding_migrate_vendor") or "").strip()
        if migrate_vendor:
            rmc_ob["migration"] = {
                "vendor_slug": migrate_vendor,
                "profile_slug": request.session.get("onboarding_migrate_profile"),
                "source_system": request.session.get("onboarding_migrate_source_system"),
                "domains": request.session.get("onboarding_migrate_domains") or [],
                "started_from": "public_onboarding",
            }
        school_settings["rmc_public_onboarding"] = rmc_ob
    # Wave L7: persist migration intent in the lifecycle-spine-readable
    # shape so apps.lifecycle.signals.school_post_save_record_lifecycle
    # auto-launches a draft MigrationBundle on creation.
    if migration_vendor:
        school_settings["migration_intent"] = {
            "vendor": migration_vendor,
            "intake_method": "file_upload",
            "expected_students": 0,
            "label": f"{name} initial migration from {migration_vendor}"[:200],
        }
    country_defaults = GlobalGeoCatalog.country_defaults(country_code)
    create_kwargs = dict(
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
    # Wave L7: school-type maps to first-class primary_sector so the
    # blueprint selector picks the right starter pack on first login.
    if school_type:
        create_kwargs["primary_sector"] = _SCHOOL_TYPE_TO_PRIMARY_SECTOR.get(
            school_type, ""
        )[:64]
    school = School.objects.create(**create_kwargs)
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
        # v3.58.x Wave 9 Agent K — async_send=True moves the SMTP attempt
        # off the request lifecycle so a hung / blocked / misconfigured
        # SMTP host can NEVER stall the signup POST past the gateway
        # timeout (the "network unreachable" symptom the user reported
        # was caused by the BACKOFF list [1, 5, 30] running synchronously
        # on top of a 10s socket timeout — ≈46s worst case, well past
        # Render's 30s HTTP gateway cutoff). The async daemon thread
        # runs the canonical retry sequence and writes an
        # EmailDeliveryEvent audit row on completion; operators monitor
        # delivery via the email-health + signup-diagnostics dashboards.
        send_transactional(
            subject=subject,
            body=body,
            to=email,
            from_email=settings.DEFAULT_FROM_EMAIL or "noreply@runmycampus.com",
            priority="transactional",
            async_send=True,
        )
    except (OSError, ConnectionError, ValueError, TypeError):
        pass

    t1 = time.monotonic()
    request_latency_ms = int((t1 - t0) * 1000)
    logger.info(
        "signup_school request_latency_ms=%d outcome=success",
        request_latency_ms,
    )

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
    # Wave L7 — build a richer success context so the done page can
    # render a "what happens next" timeline + workspace URL preview +
    # migration-aware CTA.
    workspace_url = ""
    base_domain = (getattr(settings, "MULTI_TENANT_BASE_DOMAIN", "") or "").strip().lower()
    if base_domain:
        workspace_url = f"https://{subdomain}.{base_domain}"
    return render(
        request,
        "schools/signup_school_done.html",
        {
            "email": email,
            "school_name": name,
            "workspace_url": workspace_url,
            "school_slug": slug,
            "migration_vendor": migration_vendor,
            "school_type": school_type,
            "country_code": country_code,
        },
    )


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


def _get_blueprint_packs_for_onboarding(country_code: str):
    """
    Pass 7: surface a short list of BlueprintPacks for the wizard step-2 picker.

    Ranks packs by country relevance: an exact country_code match goes first,
    then packs whose supported_country_scope is empty (= global), then the rest.
    Caps at 12 to keep the picker scannable.
    """
    try:
        from apps.policies.models import BlueprintPack
    except (ImportError, ModuleNotFoundError):
        return []
    try:
        qs = list(BlueprintPack.objects.filter(is_active=True).order_by("category", "name")[:60])
    except Exception:
        return []
    cc = (country_code or "").strip().upper()
    primary, global_packs, rest = [], [], []
    for pack in qs:
        pack_cc = (getattr(pack, "country_code", "") or "").strip().upper()
        scope = getattr(pack, "supported_country_scope", None) or []
        if cc and (pack_cc == cc or cc in [str(s).upper() for s in scope if s]):
            primary.append(pack)
        elif not scope and not pack_cc:
            global_packs.append(pack)
        else:
            rest.append(pack)
    ranked = primary + global_packs + rest
    return ranked[:12]


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
    # v3.17 (2026-05-17): Migration step inserted as step 3. Review becomes
    # step 4. The expansion is bounded by ONBOARDING_TOTAL_STEPS so the
    # progress indicator and the back-button affordances stay in sync.
    try:
        step = max(1, min(ONBOARDING_TOTAL_STEPS, int(step_raw)))
    except (TypeError, ValueError):
        step = 1

    plans = _get_plans_for_onboarding()
    templates = _get_templates_for_onboarding()
    blueprint_packs = _get_blueprint_packs_for_onboarding(
        session.get("onboarding_country_code") or ""
    )

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
            # Pass 7: blueprint pack picker — persist the chosen pack slug so it
            # can be applied during provisioning (apply_blueprint_pack).
            session["onboarding_pack_slug"] = (
                request.POST.get("pack_slug") or ""
            ).strip() or None
            session["onboarding_step"] = ONBOARDING_STEP_MIGRATION
            session.modified = True
            return redirect(
                reverse("onboard_wizard") + f"?step={ONBOARDING_STEP_MIGRATION}"
            )
        if step == ONBOARDING_STEP_MIGRATION:
            # v3.17: Migration step. User picks a vendor (or "spreadsheet"
            # for CSV/Excel/other) OR clicks "set up later". The intent
            # persists in session and is carried into school.settings via
            # signup_school so verify_signup can route to the handoff page
            # after magic-link activation.
            skip = request.POST.get("skip_migration") in ("1", "true", "on")
            chosen_slug = (request.POST.get("vendor_slug") or "").strip().lower()
            chosen = resolve_vendor(chosen_slug) if chosen_slug else None
            if skip or not chosen:
                session["onboarding_migrate_vendor"] = None
                session["onboarding_migrate_profile"] = None
                session["onboarding_migrate_source_system"] = None
                session["onboarding_migrate_domains"] = []
            else:
                session["onboarding_migrate_vendor"] = chosen.slug
                session["onboarding_migrate_profile"] = chosen.profile_slug
                session["onboarding_migrate_source_system"] = chosen.source_system
                # Default to the all-quick + standard domains pre-checked
                # (matches OnboardingDataDomain.default_on); the handoff page
                # lets the operator toggle individuals.
                session["onboarding_migrate_domains"] = [
                    d.slug for d in ONBOARDING_DATA_DOMAINS if d.default_on
                ]
            session["onboarding_step"] = ONBOARDING_STEP_REVIEW
            session.modified = True
            return redirect(
                reverse("onboard_wizard") + f"?step={ONBOARDING_STEP_REVIEW}"
            )
        if step == ONBOARDING_STEP_REVIEW:
            # Pass 7: sample-data toggle — persist the choice and forward to the
            # signup form (which carries it into school.settings.rmc_public_onboarding).
            session["onboarding_sample_data"] = request.POST.get("sample_data") in (
                "1",
                "true",
                "on",
            )
            session.modified = True
            signup_target = reverse("signup_school")
            cid = session.get("onboarding_correlation_id")
            if cid:
                signup_target += f"?ob={str(cid)[:12]}"
            return redirect(signup_target)

    if session.get("onboarding_country_code"):
        _apply_onboarding_region_defaults(
            session,
            plans,
            templates,
            session.get("onboarding_country_code") or "",
        )

    _maybe_emit_onboarding_start(request, session)
    if step == ONBOARDING_STEP_REVIEW and session.get("onboarding_country_code"):
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

    # v3.17 (2026-05-17): vendor + step-indicator context for the migration step.
    selected_vendor_slug = session.get("onboarding_migrate_vendor")
    selected_vendor = resolve_vendor(selected_vendor_slug) if selected_vendor_slug else None
    wizard_steps = [
        {"id": 1, "label": "Region"},
        {"id": 2, "label": "Plan"},
        {"id": ONBOARDING_STEP_MIGRATION, "label": "Migration"},
        {"id": ONBOARDING_STEP_REVIEW, "label": "Review"},
    ]

    return render(
        request,
        "schools/onboard_wizard.html",
        {
            "step": step,
            "wizard_steps": wizard_steps,
            "wizard_total_steps": ONBOARDING_TOTAL_STEPS,
            "trial_endpoint": reverse("api_trial_school"),
            "signup_url": signup_url,
            "countries": countries[:120],
            "default_country_code": default_country,
            "plans": plans,
            "templates": templates,
            "blueprint_packs": blueprint_packs,
            "onboarding_country_code": session.get("onboarding_country_code"),
            "onboarding_school_flavor": session.get(
                "onboarding_school_flavor", "general"
            ),
            "onboarding_plan_slug": session.get("onboarding_plan_slug"),
            "onboarding_trial": session.get("onboarding_trial", False),
            "onboarding_template_slug": session.get("onboarding_template_slug"),
            "onboarding_pack_slug": session.get("onboarding_pack_slug"),
            "onboarding_sample_data": session.get("onboarding_sample_data", False),
            "website_import_doc_url": "#",
            "onboarding_import_primary_color": session.get(
                "onboarding_import_primary_color"
            ),
            "onboarding_import_logo_url": session.get("onboarding_import_logo_url"),
            "onboarding_import_site_name": session.get("onboarding_import_site_name"),
            "onboarding_correlation_id": session.get("onboarding_correlation_id"),
            # v3.17 migration-step context
            "vendors": ONBOARDING_VENDORS,
            "selected_vendor": selected_vendor,
            "selected_vendor_slug": selected_vendor_slug,
            "data_domains": ONBOARDING_DATA_DOMAINS,
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
        # tenant-isolation-allow: view-layer-scoped-via-request-school-or-role-graph
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

    # v3.58.x Wave 9 Agent K — route provisioning through the canonical
    # ``dispatch_provision_school`` so it queues via Celery when the
    # broker is reachable (returning immediately to the operator) and
    # falls back to synchronous-in-request only when Celery is fully
    # unavailable. The sync fallback was the v3.57 status quo from
    # this view and is preserved as a last resort — but on Render +
    # other PaaS deployments where Celery + Redis broker are wired up,
    # the verify-link click will now return in well under a second.
    try:
        from apps.schools.tasks import dispatch_provision_school

        dispatch_provision_school(
            str(school.id), contact_email=verification.email,
        )
    except (ImportError, AttributeError, TypeError, ValueError, OSError):
        pass

    # Pass 7: magic-link login — verifying the email proves ownership, so log the
    # newly-provisioned admin in directly instead of bouncing through a password
    # form they cannot satisfy (admin user is created with set_unusable_password
    # in apps/schools/tasks.py). Falls back to the legacy login redirect when the
    # admin user cannot be resolved.
    User = get_user_model()
    admin_user = (
        User.objects.filter(email__iexact=verification.email).order_by("id").first()
    )
    if admin_user is not None and admin_user.is_active:
        try:
            auth_login(request, admin_user)
        except (ValueError, TypeError, AttributeError):
            admin_user = None

    if admin_user is not None and admin_user.is_active:
        # v3.17 (2026-05-17): if the new admin asked to migrate from another
        # platform during onboarding, route them to the handoff page before
        # the dashboard so they land in Migration Cloud with their vendor +
        # data-domain selection pre-bound. Dashboard remains the fallback.
        migration_intent = ((school.settings or {}).get("rmc_public_onboarding") or {}).get(
            "migration"
        )
        if migration_intent and migration_intent.get("vendor_slug"):
            try:
                return redirect(reverse("onboard_migration_handoff"))
            except NoReverseMatch:
                pass  # fall through to dashboard
        for url_name in ("studio_os:launch", "accounts:backend_dashboard"):
            try:
                return redirect(reverse(url_name))
            except NoReverseMatch:
                continue
        return redirect("/")

    login_url = (settings.LOGIN_URL or "/authentication/login/").lstrip("/")
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


# ───────────────────────────────────────────────────────────────────────────
# v3.17 (2026-05-17) — Migration handoff after magic-link verification.
#
# Two views:
#   onboard_migration_handoff (GET)     → render the handoff page
#   onboard_migration_start    (POST)   → create MigrationBundle, jump to MC
#
# Triggered by verify_signup when school.settings.rmc_public_onboarding.migration
# was set in the public wizard. The handoff page reads the same source-of-truth
# so the operator can adjust their domain selection before kicking off, but the
# rule is: ONE click should be enough to start migration from this page.
# ───────────────────────────────────────────────────────────────────────────


def _school_for_authenticated_admin(request: HttpRequest):
    """Locate the school whose signup just completed for the current user.

    Order of resolution:
      1. ``request.school`` (multi-tenant middleware sets this when present).
      2. A School whose creator/admin matches request.user (covers self-service
         signup before tenant DNS is configured — common on day 0).
      3. The user's owned schools, most-recent first.
    Returns None if no plausible match exists.
    """
    school = getattr(request, "school", None)
    if school is not None:
        return school
    user = getattr(request, "user", None)
    if not getattr(user, "is_authenticated", False):
        return None
    # Match by signup verification email — the magic-link recipient is the
    # admin we just activated. SignupVerification stores email + school FK.
    # tenant-isolation-allow: view-layer-scoped-via-request-school-or-role-graph
    sv = (
        SignupVerification.objects.filter(email__iexact=user.email)
        .select_related("school")
        .order_by("-created_at")
        .first()
    )
    return sv.school if sv else None


@require_GET
def onboard_migration_handoff(request: HttpRequest):
    """Post-verification migration handoff page.

    Shows the vendor confirmation chip + the data-domain checklist + one-click
    "Start migration" CTA. Operators arriving here picked a vendor during the
    public onboarding wizard. If they didn't (or settings got cleared), we
    fall back to a generic "Pick a vendor" tile grid — the same one the
    wizard step 3 uses — so this page is always usable as a standalone
    surface (e.g. linked from a dashboard "complete your setup" banner).
    """
    user = getattr(request, "user", None)
    if not getattr(user, "is_authenticated", False):
        login_url = (settings.LOGIN_URL or "/authentication/login/").lstrip("/")
        return redirect(
            f"/{login_url}?next={reverse('onboard_migration_handoff')}"
        )

    school = _school_for_authenticated_admin(request)
    intent = {}
    if school is not None:
        intent = ((school.settings or {}).get("rmc_public_onboarding") or {}).get(
            "migration"
        ) or {}

    selected_vendor_slug = (intent.get("vendor_slug") or "").strip().lower()
    selected_vendor = resolve_vendor(selected_vendor_slug) if selected_vendor_slug else None
    selected_domain_slugs = set(intent.get("domains") or [])
    if not selected_domain_slugs:
        # First-time landings (or "set up later" fallbacks) pre-check the
        # default-on subset so the operator sees a sensible starting state.
        selected_domain_slugs = {d.slug for d in ONBOARDING_DATA_DOMAINS if d.default_on}

    minutes_total = estimate_minutes(list(selected_domain_slugs))

    return render(
        request,
        "schools/onboard_migration_handoff.html",
        {
            "school": school,
            "selected_vendor": selected_vendor,
            "selected_vendor_slug": selected_vendor_slug,
            "vendors": ONBOARDING_VENDORS,
            "data_domains": ONBOARDING_DATA_DOMAINS,
            "selected_domain_slugs": selected_domain_slugs,
            "minutes_total": minutes_total,
            "dashboard_url": (
                reverse("accounts:backend_dashboard")
                if _url_exists("accounts:backend_dashboard")
                else "/"
            ),
        },
    )


def _url_exists(name: str) -> bool:
    """Reverse-with-fallback so handoff degrades cleanly if a target route is missing."""
    try:
        reverse(name)
        return True
    except NoReverseMatch:
        return False


@require_POST
def onboard_migration_start(request: HttpRequest):
    """One-click bundle creation from the handoff page.

    Reads vendor + domain selection from POST, persists the final selection
    onto school.settings (so re-landings show the operator's adjusted state),
    and deep-links into the Migration Cloud intake wizard with everything
    pre-filled via query string. The intake view honours vendor / school_id
    / source_hint / profile parameters added in this wave.

    Why we don't directly create a MigrationBundle here:
      - The intake wizard is the SOT for bundle creation (intake_method
        validation, idempotency keys, artifact upload, AI plan kickoff).
        Going through it preserves that contract instead of forking it.
      - Deep-linking with pre-filled params gives the operator one final
        confirmation point — important for trust on the first migration.
    """
    user = getattr(request, "user", None)
    if not getattr(user, "is_authenticated", False):
        return redirect(reverse("onboard_migration_handoff"))

    school = _school_for_authenticated_admin(request)
    vendor_slug = (request.POST.get("vendor_slug") or "").strip().lower()
    vendor = resolve_vendor(vendor_slug) if vendor_slug else None
    domain_slugs = [
        s for s in request.POST.getlist("domains") if s in DOMAINS_BY_SLUG
    ]

    # Persist the operator's final selection so a return visit shows it.
    if school is not None and vendor is not None:
        school_settings = dict(school.settings or {})
        rmc_ob = dict(school_settings.get("rmc_public_onboarding") or {})
        rmc_ob["migration"] = {
            "vendor_slug": vendor.slug,
            "profile_slug": vendor.profile_slug,
            "source_system": vendor.source_system,
            "domains": domain_slugs,
            "started_from": "onboarding_handoff",
            "started_at": timezone.now().isoformat(),
        }
        school_settings["rmc_public_onboarding"] = rmc_ob
        school.settings = school_settings
        school.save(update_fields=["settings", "updated_at"])

    # Skip-for-now button → land on dashboard.
    if request.POST.get("skip") in ("1", "true", "on") or vendor is None:
        try:
            return redirect(reverse("accounts:backend_dashboard"))
        except NoReverseMatch:
            return redirect("/")

    # Deep-link into Migration Cloud intake with everything pre-bound.
    try:
        intake_url = reverse("migration_cloud_super:bundle_new")
    except NoReverseMatch:
        try:
            intake_url = reverse("migration_cloud_portal:bundle_new")
        except NoReverseMatch:
            # Fall back to the operator dashboard if MC isn't routed in
            # this deployment (defensive — MC ships with the platform).
            try:
                return redirect(reverse("accounts:backend_dashboard"))
            except NoReverseMatch:
                return redirect("/")

    # Build the pre-fill query string.
    from urllib.parse import urlencode

    qs = {
        "vendor": vendor.slug,
        "source_hint": vendor.source_system,
    }
    if vendor.profile_slug:
        qs["profile"] = vendor.profile_slug
    if school is not None and getattr(school, "id", None):
        qs["school_id"] = str(school.id)
    if domain_slugs:
        qs["domains"] = ",".join(domain_slugs)

    return redirect(f"{intake_url}?{urlencode(qs)}")


# ───────────────────────────────────────────────────────────────────────────
# v3.57.x Wave 8 (2026-05-22) — Live slug-availability check for signup form.
#
# Powers the inline pill next to the slug input on the public signup form.
# Public, GET-only, rate-limited at 60/min/IP. Returns normalized slug +
# availability + suggestions when taken. Reserved slugs (admin, api, www, …)
# never read as available so the operator never accidentally collides with
# platform-reserved routes.
# ───────────────────────────────────────────────────────────────────────────

_RESERVED_SLUGS = (
    "admin",
    "api",
    "www",
    "manager",
    "super",
    "auth",
    "login",
    "signup",
    "marketing",
    "static",
    "media",
    "metrics",
    "health",
)


@never_cache
@require_GET
@ratelimit(key="ip", rate="60/m", method="GET", block=True)
def signup_slug_check(request: HttpRequest) -> JsonResponse:
    """Live slug-availability JSON endpoint for the signup form.

    Query params:
        slug         – the candidate slug (required for a meaningful answer)
        country_code – optional 2-letter ISO code; when present, an extra
                       country-suffixed suggestion is offered if the slug is
                       taken.

    Response shape:
        {
          "slug": <normalized>,
          "available": <bool>,
          "reason": "taken" | "invalid" | null,
          "suggestions": [<str>, ...]    # up to 3, all currently free
        }
    """
    from django.utils.text import slugify as _dj_slugify

    raw = (request.GET.get("slug") or "").strip()
    normalized = _dj_slugify(raw)[:120]

    if not normalized or normalized in _RESERVED_SLUGS:
        return JsonResponse(
            {
                "slug": normalized,
                "available": False,
                "reason": "invalid",
                "suggestions": [],
            }
        )

    # tenant-isolation-allow: public-slug-availability-lookup-no-tenant-scope
    taken = (
        School.objects.filter(slug=normalized).exists()
        # tenant-isolation-allow: public-slug-availability-lookup-no-tenant-scope
        or School.objects.filter(subdomain=normalized).exists()
    )

    if not taken:
        return JsonResponse(
            {
                "slug": normalized,
                "available": True,
                "reason": None,
                "suggestions": [],
            }
        )

    country_code = (request.GET.get("country_code") or "").strip()[:2].lower()
    candidates = [
        f"{normalized}-school",
        f"{normalized}2",
        f"{normalized}-academy",
    ]
    if country_code and country_code.isalpha() and len(country_code) == 2:
        candidates.append(f"{normalized}-{country_code}")

    suggestions = []
    for cand in candidates:
        cand_norm = _dj_slugify(cand)[:120]
        if not cand_norm or cand_norm in _RESERVED_SLUGS:
            continue
        if cand_norm in suggestions:
            continue
        # tenant-isolation-allow: public-slug-availability-lookup-no-tenant-scope
        cand_taken = (
            School.objects.filter(slug=cand_norm).exists()
            # tenant-isolation-allow: public-slug-availability-lookup-no-tenant-scope
            or School.objects.filter(subdomain=cand_norm).exists()
        )
        if not cand_taken:
            suggestions.append(cand_norm)
        if len(suggestions) >= 3:
            break

    return JsonResponse(
        {
            "slug": normalized,
            "available": False,
            "reason": "taken",
            "suggestions": suggestions,
        }
    )
