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
from django.db import DatabaseError, IntegrityError, transaction
from django.db.transaction import TransactionManagementError
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
from apps.schools.compliance_region import derive_compliance_region
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

    Lists ALL ISO 3166-1 countries (name-sorted by the catalog). Returns an
    empty list on ANY failure (catalog deps unavailable, DB unreachable, etc.)
    — the signup template's free-text input fallback activates in that case.

    NB: do NOT re-introduce a row cap here. A prior ``rows[:120]`` slice
    silently truncated the name-sorted catalog at the 120th country (~Kuwait),
    so every country after it (Kyrgyzstan→Zimbabwe) vanished from the signup
    dropdown. There are only ~249 countries; render them all.
    """
    try:
        from apps.siteconfig.global_catalog import GlobalGeoCatalog

        rows = GlobalGeoCatalog.list_countries() or []
        out: list[dict[str, str]] = []
        for row in rows:
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
    except (DatabaseError, ImportError, AttributeError, TypeError, ValueError):
        return []


def _validate_signup_country_code(country_code: str) -> str | None:
    """
    Public signup requires an ISO 3166-1 alpha-2 country so default_region,
    currency, calendar pack, and compliance_region resolve on first save.
    """
    cc = (country_code or "").strip().upper()
    if not cc:
        return "Country is required."
    if len(cc) != 2 or not cc.isalpha():
        return "Enter a valid two-letter country code."
    catalog_rows = _signup_countries()
    if catalog_rows:
        known = {str(row.get("iso_alpha2") or "").upper() for row in catalog_rows}
        if cc not in known:
            return "Select a valid country from the list."
        return None
    alpha3 = GlobalGeoCatalog.normalize_country_code(cc)
    if len(alpha3) != 3:
        return "Select a valid country from the list."
    return None


from apps.schools.models import School, SignupVerification, TenantInvite
from apps.schools.onboarding_vendors import (
    DOMAINS_BY_SLUG,
    ONBOARDING_DATA_DOMAINS,
    ONBOARDING_VENDORS,
    estimate_minutes,
    resolve_vendor,
)
from apps.siteconfig.global_catalog import GlobalGeoCatalog
# v3.62.2 — country-adaptive calendar + school-type cards on /signup/.
# v3.62.8 (Wave 6) — language picker + per-language education-system overlay.
from apps.siteconfig.country_localization_service import (
    get_default_calendar_code,
    get_default_language,
    get_india_state_options,
    parse_signup_language_selection,
    resolve_country_pack,
    resolve_language_pack,
    resolve_primary_sector_for_school_type,
    validate_calendar_code,
    validate_language_code,
    validate_school_type,
)
from apps.governance.country_matrix_service import signup_governance_defaults
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


def _signup_localization_json(request: HttpRequest, cc: str, country_pack: dict) -> str:
    """Embedded bootstrap for rmc-signup-country-adapter (offline-first fallback)."""
    from apps.siteconfig.signup_localization_bootstrap import signup_localization_json

    return signup_localization_json(request, cc, country_pack)


def _signup_decisions_model(
    country_code: str,
    country_pack: dict | None = None,
    *,
    cycles: list[str] | None = None,
    funding: str = "",
    campus_count: int = 0,
) -> dict:
    """Progressive decision model for the setup step — recommended option per
    decision, auto-applied defaults, and which questions to even ask.

    Pure and DB-free; the ``/signup/decisions/`` endpoint calls the same engine,
    so the server-rendered "Recommended" badges match the ones the form redraws
    live as earlier answers change. Region is lifted from the resolved country
    pack so connectivity/governance defaults sharpen without another lookup.
    """
    from apps.schools.onboarding_decisions import build_onboarding_decisions

    region_key = ""
    source = str((country_pack or {}).get("_source") or "")
    if source.startswith("regional:"):
        region_key = source.split(":", 1)[1]
    return build_onboarding_decisions(
        country_code=country_code or "",
        region_key=region_key,
        education_cycles=list(cycles or []),
        funding_type=funding or "",
        institution_profile={"campus_count": campus_count or 0},
    )


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

# Which record families a school can declare it's bringing over, captured at
# signup alongside the vendor so the auto-drafted MigrationBundle knows scope
# from day one. Kept in sync with the checkbox group in signup_school.html.
_SIGNUP_DOMAIN_SLUGS = {
    "students", "guardians", "staff", "enrollments", "grades",
    "attendance", "timetable", "fees", "discipline", "health",
}


def _clean_migration_domains(raw) -> list[str]:
    """Validate the optional 'which records to import' multi-select from signup.

    Preserves declared order, de-dupes, drops anything not in the allowlist.
    Never raises — an absent/garbage field just yields an empty list.
    """
    seen: set[str] = set()
    out: list[str] = []
    for item in raw or []:
        slug = (item or "").strip().lower()
        if slug in _SIGNUP_DOMAIN_SLUGS and slug not in seen:
            seen.add(slug)
            out.append(slug)
    return out


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
    except (AttributeError, IndexError, TypeError, ValueError):
        pass
    return ""


def _assign_data_residency_or_record_failure(school) -> bool:
    """Assign regulatory data region or record a FAILED audit event.

    v4.00.3 audit (2026-05-28): the prior catch-all ``pass`` around the
    data-residency call masked any assignment failure — the
    school stayed ``data_region=None`` with no log, no event, no operator
    signal. For a platform with GDPR / cross-border data-sovereignty
    obligations this is load-bearing: a silently-misassigned school can
    end up storing data in the wrong region. Returns True on success,
    False when the failure was recorded.
    """
    try:
        from apps.schools.data_residency_onboarding import (
            apply_data_residency_for_new_school,
        )

        apply_data_residency_for_new_school(school, source="public_signup")
        school.save(update_fields=["data_region", "settings"])
        return True
    except (ImportError, AttributeError, ValueError, TypeError, OSError) as exc:
        logger.warning(
            "signup data_residency assignment failed school_id=%s err=%s",
            school.id,
            type(exc).__name__,
            exc_info=True,
        )
        try:
            from apps.schools.models import SchoolProvisioningEvent

            SchoolProvisioningEvent.log_event(
                school=school,
                event_type=SchoolProvisioningEvent.EventType.FAILED,
                status=SchoolProvisioningEvent.Status.WARNING,
                message="Data residency assignment failed during signup",
                payload={
                    "phase": "data_residency",
                    "error_type": type(exc).__name__,
                    "error": str(exc)[:500],
                },
            )
        except (ImportError, AttributeError, TypeError, ValueError, OSError):
            pass
        return False


def _signup_rate_limited_response(request, scope: str, *, json_response: bool):
    """Per-IP throttle for the UNAUTHENTICATED tenant-creation entry points.

    Without this, anyone can POST in a loop to: squat school slugs, exhaust the
    free-tier schema namespace, and — most damaging — make the platform fire
    verification emails at arbitrary addresses (a spam cannon). Returns a 429
    response when over the limit, else ``None``.

    Limits are settings-configurable so an operator can raise them for a
    high-volume partner integration; the cache-backed throttle fails OPEN if the
    cache is unavailable, so a cache blip never blocks legitimate signups.
    """
    from apps.api.rate_limit import throttle_ip_request

    max_count = int(getattr(settings, "SIGNUP_MAX_PER_WINDOW", 10))
    window = int(getattr(settings, "SIGNUP_RATE_WINDOW_SECONDS", 3600))
    allowed, retry_after = throttle_ip_request(
        request, scope=scope, max_count=max_count, window_seconds=window
    )
    if allowed:
        return None
    logger.warning("signup.rate_limited scope=%s", scope)
    if json_response:
        resp = JsonResponse(
            {
                "ok": False,
                "error": "rate_limited",
                "detail": "Too many signup attempts. Please try again later.",
                "retry_after": retry_after,
            },
            status=429,
        )
    else:
        messages.error(
            request,
            "Too many signup attempts from your network. "
            "Please wait a few minutes and try again.",
        )
        resp = redirect(request.path)
    resp["Retry-After"] = str(retry_after)
    return resp


@require_http_methods(["GET", "POST"])
@transaction.atomic
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
        # v3.62.2: term_preset is now country-pack-driven. We don't enforce a
        # narrow ("", "UK") allowlist anymore — the country-localization
        # service decides what calendar codes are valid for the selected
        # country. Empty string still means "use country default".
        tp = (request.GET.get("term_preset") or "").strip()[:48]
        name = (request.GET.get("name") or request.GET.get("school_name") or "").strip()[
            :200
        ]
        email = (request.GET.get("email") or "").strip()[:254]  # magic-number-allow: string-truncation-cap
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
        # v3.62.2 — country-adaptive calendar + school-type cards. Resolve
        # the country pack for the initial country (Accept-Language / session
        # / explicit query param) so the cards render localized on first paint
        # without requiring a JS round-trip. The adapter JS re-renders these
        # in place when the operator picks a different country.
        #
        # v3.62.8 (Wave 6) — also resolve language picker. For multilingual
        # countries the language picker shows all official languages and the
        # per-language education-system overlay (CM Anglo/Franco, CA EN/FR,
        # BE NL/FR/DE, CH 4 lang, IN 11 lang, etc.). Default-language pre-pick
        # is the country's `is_default` flag; user-saved preference (session
        # cookie) wins when present.
        language_code = (
            (request.session.get("onboarding_language") or "").strip().lower()
            or get_default_language(cc)
        )
        if validate_language_code(cc, language_code):
            country_pack = resolve_language_pack(cc, language_code)
        else:
            country_pack = resolve_country_pack(cc)
            language_code = ""
        language_codes_csv = language_code or get_default_language(cc)
        if not language_codes_csv:
            language_codes_csv = ""
        primary_language_code = language_codes_csv
        if not tp:
            tp = get_default_calendar_code(cc)
        signup_localization_json = _signup_localization_json(request, cc, country_pack)
        decisions_model = _signup_decisions_model(cc, country_pack)
        return render(
            request,
            "schools/signup_school.html",
            {
                "country_code": cc,
                "term_preset": tp,
                # Progressive decision model: recommended option per decision,
                # country-auto-applied defaults, and the ask/skip split. The
                # template pre-selects + badges from this; JS refreshes it from
                # /signup/decisions/ as earlier answers change.
                "decisions": decisions_model,
                "decision_recommended": decisions_model["recommended"],
                "decision_auto": decisions_model["auto_applied"],
                "language_code": language_code,
                "language_codes_csv": language_codes_csv,
                "primary_language_code": primary_language_code,
                "signup_localization_json": signup_localization_json,
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
                # v3.62.2 local-first: country-adaptive pack drives card grids.
                # v3.62.8 (Wave 6) — also carries `languages` overlay so the
                # picker can render per-language cards server-side without
                # waiting on a JS round-trip.
                "country_pack": country_pack,
                # Wave 14 (v3.62.19) — India per-state mini-picker. Always
                # shipped; the template gates it from the resolved country pack with zero cost
                # to non-IN visitors. List is sorted alphabetically by state
                # name; each entry carries the calendar_code that auto-fills
                # the calendar radio when the operator picks their state.
                "india_state_options": get_india_state_options(),
                "governance_matrix_hint": signup_governance_defaults(cc),
            },
        )

    # Abuse defense: throttle per IP before creating a school or sending the
    # verification email (slug squatting / free-tier exhaustion / email spam).
    throttled = _signup_rate_limited_response(
        request,
        "signup_school",
        json_response=request.headers.get("Accept", "").find("application/json") >= 0,
    )
    if throttled is not None:
        return throttled

    name = (request.POST.get("name") or "").strip()
    slug = (request.POST.get("slug") or "").strip() or _slug_from_name(name)
    email = (request.POST.get("email") or "").strip()
    country_code = (request.POST.get("country_code") or "").strip()[:2].upper()
    # v3.62.2 — calendar code is now country-pack-driven. The localization
    # service validates against the country's allowed list and rejects
    # anything not in that list (silently empties so we fall back to the
    # country default).
    term_preset_raw = (request.POST.get("term_preset") or "").strip()[:48]
    term_preset = validate_calendar_code(country_code, term_preset_raw)
    if not term_preset:
        # Preserve the legacy "UK" alias for any old client still posting
        # the v3.61.x term_preset value.
        if term_preset_raw.upper() in ("UK", "GB"):
            term_preset = "uk-3-term"
    signup_ref = (request.POST.get("signup_ref") or "").strip()[:32]
    # Wave L7 — intent capture for downstream auto-launch hooks.
    raw_migration_vendor = (request.POST.get("migration_vendor") or "").strip().lower()
    migration_vendor_invalid = bool(
        raw_migration_vendor and raw_migration_vendor not in _SIGNUP_VENDOR_SLUGS
    )
    migration_vendor = "" if migration_vendor_invalid else raw_migration_vendor
    # Optional "which records to import" multi-select captured next to the vendor.
    raw_migration_domains = request.POST.getlist("migration_domains")
    # v3.62.2 — school_type validated against the COUNTRY's pack first; if
    # not present there, fall back to the legacy hardcoded map so existing
    # bookmarked-form clients keep working.
    # v4.00.27 (2026-05-29) — multi-select aware. The signup form now sends
    # a checkbox group instead of a single radio so a school can declare
    # every cycle it covers (Cameroon comprehensive lycée: 1er + 2ème
    # cycle; Nigeria full school: nursery + primary + JSS + SSS; US K-12:
    # elementary + middle + high; etc.). We accept getlist() AND fall back
    # to the legacy single-value POST so older bookmarked forms still work.
    raw_multi = [s.strip().lower() for s in request.POST.getlist("school_type") if s and s.strip()]
    if not raw_multi:
        single = (request.POST.get("school_type") or "").strip().lower()
        if single:
            raw_multi = [single]

    validated_types = []
    for cand in raw_multi:
        v = validate_school_type(country_code, cand)
        if not v and cand in _SCHOOL_TYPE_TO_PRIMARY_SECTOR:
            v = cand
        if v and v not in validated_types:
            validated_types.append(v)

    # `school_type` (singular) preserves the legacy contract used downstream
    # for primary_sector resolution and lifecycle hooks — it carries the
    # FIRST selected cycle. The full list is preserved in `school_type_raw`
    # below (pipe-joined) for the create-time M2M sync and is round-tripped
    # back to the template on validation re-render so the user's checkbox
    # selections survive POST-error reloads.
    school_type = validated_types[0] if validated_types else ""
    school_type_raw = "|".join(validated_types)

    # v4.02.51 (2026-06-02) — multi-language signup. Operators may select every
    # official language their school uses; primary (★) drives education-system
    # overlay + School.primary_language (India state picker auto-stars regional
    # language of instruction when it is among the selected codes).
    india_state = (request.POST.get("india_state") or "").strip().upper()[:8]
    region_hint = (request.POST.get("signup_region_hint") or request.GET.get("region") or "").strip()[:64]
    language_codes, language_code = parse_signup_language_selection(
        country_code=country_code,
        language_codes=request.POST.getlist("language_codes"),
        primary_language_code=(request.POST.get("primary_language_code") or "").strip().lower()[:8],
        language_code_legacy=(request.POST.get("language_code") or "").strip().lower()[:8],
        state_code=india_state,
        region_hint=region_hint,
    )
    language_codes_csv = "|".join(language_codes)
    primary_language_code = language_code

    from apps.schools.onboarding_profile import normalize_institution_profile

    profile_result = normalize_institution_profile(
        {
            "funding_type": request.POST.get("funding_type"),
            "organization_scope": request.POST.get("organization_scope"),
            "learner_scale": request.POST.get("learner_scale"),
            "student_capacity": request.POST.get("student_capacity"),
            "lms_preference": request.POST.get("lms_preference"),
            "campus_count": request.POST.get("campus_count"),
            "staff_count": request.POST.get("staff_count"),
            "operating_model": request.POST.get("operating_model"),
            "operational_services": request.POST.getlist("operational_services"),
            "connectivity_profile": request.POST.get("connectivity_profile"),
            "payment_profile": request.POST.get("payment_profile"),
            "assessment_profile": request.POST.get("assessment_profile"),
            "identity_profile": request.POST.get("identity_profile"),
            "data_residency_requirement": request.POST.get("data_residency_requirement"),
            "accessibility_profile": request.POST.get("accessibility_profile"),
            "migration_complexity": request.POST.get("migration_complexity"),
            "automation_preference": request.POST.get("automation_preference"),
            "go_live_timeline": request.POST.get("go_live_timeline"),
            "session_pattern": request.POST.get("session_pattern"),
            "curriculum_board": request.POST.get("curriculum_board"),
            "governance_profile": request.POST.get("governance_profile"),
            "migration_vendor": migration_vendor,
            "migration_domains": raw_migration_domains,
        },
        strict=True,
    )
    institution_profile = dict(profile_result.values)
    funding_type = institution_profile["funding_type"]
    organization_scope = institution_profile["organization_scope"]
    learner_scale = institution_profile["learner_scale"]
    student_capacity = institution_profile["student_capacity"]
    lms_preference = institution_profile["lms_preference"]
    campus_count = institution_profile["campus_count"]
    staff_count = institution_profile["staff_count"]
    operating_model = institution_profile["operating_model"]
    operational_services = institution_profile["operational_services"]
    connectivity_profile = institution_profile["connectivity_profile"]
    payment_profile = institution_profile["payment_profile"]
    assessment_profile = institution_profile["assessment_profile"]
    identity_profile = institution_profile["identity_profile"]
    data_residency_requirement = institution_profile["data_residency_requirement"]
    accessibility_profile = institution_profile["accessibility_profile"]
    migration_complexity = institution_profile["migration_complexity"]
    automation_preference = institution_profile["automation_preference"]
    go_live_timeline = institution_profile["go_live_timeline"]
    session_pattern = institution_profile["session_pattern"]
    curriculum_board = institution_profile["curriculum_board"]
    governance_profile = institution_profile["governance_profile"]
    migration_domains = institution_profile["migration_domains"]

    errors = [issue.message for issue in profile_result.errors]
    if migration_vendor_invalid:
        errors.append("Choose a supported migration source or select Other / unsure.")
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
    country_error = _validate_signup_country_code(country_code)
    if country_error:
        errors.append(country_error)

    if errors:
        if request.headers.get("Accept", "").find("application/json") >= 0:
            return JsonResponse({"ok": False, "errors": errors}, status=400)
        for e in errors:
            messages.error(request, e)
        country_pack = resolve_country_pack(country_code)
        decisions_model = _signup_decisions_model(
            country_code,
            country_pack,
            cycles=list(validated_types),
            funding=funding_type,
            campus_count=campus_count,
        )
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
                "country_pack": country_pack,
                # Recompute the decision model from what the operator already
                # entered so their pre-selected recommendations survive a
                # validation bounce instead of resetting to the country default.
                "decisions": decisions_model,
                "decision_recommended": decisions_model["recommended"],
                "decision_auto": decisions_model["auto_applied"],
                "signup_localization_json": _signup_localization_json(
                    request, country_code, country_pack
                ),
                "school_type": school_type_raw,
                "language_codes_csv": language_codes_csv,
                "primary_language_code": primary_language_code,
                "language_code": primary_language_code,
                **institution_profile,
                "profile_validation_issues": profile_result.issue_payload(),
            },
        )
    if (
        School.objects.filter(slug=slug).exists()
        or School.objects.filter(subdomain=slug).exists()
    ):
        from apps.platform_runtime.remediation import signup_slug_taken_remediation

        remediation = signup_slug_taken_remediation(slug)
        errors.append(remediation.message)
        if request.headers.get("Accept", "").find("application/json") >= 0:
            return JsonResponse(
                {
                    "ok": False,
                    "errors": errors,
                    "remediation": remediation.to_tenant_api_dict(),
                },
                status=400,
            )
        messages.error(request, errors[0])
        country_pack = resolve_country_pack(country_code)
        decisions_model = _signup_decisions_model(
            country_code,
            country_pack,
            cycles=list(validated_types),
            funding=funding_type,
            campus_count=campus_count,
        )
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
                # v3.62.2: country pack on slug-taken re-render so cards
                # stay localized in the error state.
                "country_pack": country_pack,
                # Keep the recommended-option pre-selection through the
                # slug-taken bounce as well.
                "decisions": decisions_model,
                "decision_recommended": decisions_model["recommended"],
                "decision_auto": decisions_model["auto_applied"],
                "signup_localization_json": _signup_localization_json(
                    request, country_code, country_pack
                ),
                "school_type": school_type_raw,
                "language_codes_csv": language_codes_csv,
                "primary_language_code": primary_language_code,
                "language_code": primary_language_code,
                **institution_profile,
                "profile_validation_issues": profile_result.issue_payload(),
            },
        )

    from django.utils.text import slugify

    slug = slugify(slug) or "school"
    if not slug:
        slug = "school"
    subdomain = slug[:120]

    school_settings = {}
    # v3.62.2 — persist the resolved localization choice so downstream
    # provisioning + lifecycle signals can populate the school's calendar +
    # education levels from this country pack. Both raw codes are stored;
    # services can re-resolve labels via country_localization_service.
    # v3.62.8 (Wave 6) — also persist language_code for multilingual countries
    # so the per-language education-system overlay (CM Anglo/Franco, CA EN/FR,
    # BE NL/FR/DE, CH 4 lang, IN 11 lang) is preserved across logins.
    # PGL-009: shared builder with CLI / other create paths.
    from apps.schools.school_settings_seed import (
        build_initial_school_settings,
        resolve_school_geo_create_fields,
    )

    if country_code or term_preset or school_type or language_code or validated_types:
        school_settings = build_initial_school_settings(
            country_code=country_code or "",
            school_type_code=school_type or "",
            language_code=language_code or "",
            language_codes=list(language_codes),
            education_cycles=list(validated_types),
            calendar_code=term_preset or "",
            seed_marker="_seeded_at_signup",
            include_governance=bool(country_code),
        )
    # Backwards compatibility: keep the v3.61 term_preset hint for any code
    # path still reading school.settings["term_preset"] directly.
    if term_preset == "uk-3-term" or (term_preset_raw.upper() in ("UK", "GB")):
        school_settings["term_preset"] = "UK"
    # ``institution_profile`` is already normalized by the typed boundary above.
    # Keeping the complete v4 answer set together makes recommendation
    # recomputation deterministic and day-two review/audit possible.
    school_settings["onboarding_intent"] = {
        "country_code": country_code,
        "education_cycles": list(validated_types),
        "language_codes": list(language_codes),
        "calendar_code": term_preset,
        "institution_profile": institution_profile,
    }
    from apps.schools.onboarding_recommendations import build_onboarding_recommendations

    school_settings["recommendation_manifest"] = build_onboarding_recommendations(
        country_code=country_code,
        education_cycles=list(validated_types),
        language_codes=list(language_codes),
        institution_profile=institution_profile,
    )
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
        from apps.siteconfig.signup_localization_bootstrap import (
            build_migration_locale_context,
        )

        locale_ctx = build_migration_locale_context(
            country_code or "",
            language_code=language_code or "",
            language_codes=list(language_codes),
            calendar_code=term_preset or get_default_calendar_code(country_code),
            education_cycles=list(validated_types),
        )
        school_settings["migration_intent"] = {
            "vendor": migration_vendor,
            "intake_method": "file_upload",
            "expected_students": 0,
            "data_domains": migration_domains,
            "label": f"{name} initial migration from {migration_vendor}"[:200],
            "locale_context": locale_ctx,
        }
    country_defaults_geo = resolve_school_geo_create_fields(
        country_code, language_code=language_code or ""
    )
    create_kwargs = dict(
        name=name,
        slug=slug,
        subdomain=subdomain,
        is_active=False,
        is_approved=True,
        country_code=country_code,
        timezone=country_defaults_geo["timezone"],
        # Local-first: persist the tenant's own currency + default language from
        # the country pack at creation, so money + anonymous-visitor copy are the
        # school's locale by default instead of a global fallback. Both are blank-
        # tolerant overrides (resolve_currency / default_language doc the cascade).
        currency=country_defaults_geo["currency"],
        default_language=country_defaults_geo["default_language"],
        # Local-first: auto-assign the data-protection regime from the country (EU→GDPR,
        # US→FERPA, NG→NDPR) so masking/retention/consent apply by default instead of
        # every new tenant landing on NONE. Unmapped countries stay unset for the operator.
        # derive_compliance_region(country_code) via resolve_school_geo_create_fields
        compliance_region=country_defaults_geo["compliance_region"],
        settings=school_settings,
    )
    # Wave 6/10 (v3.62.10) — first-class primary_language. Still also lives in
    # settings.localization.language_code for backwards compat with any code
    # path that reads it from there.
    if language_code:
        create_kwargs["primary_language"] = language_code[:16]
    # v3.62.2 — primary_sector now comes from the country's pack first
    # (country-local mapping), falling back to the legacy global map. This
    # is how Nigerian "nursery"/"jss"/"sss" cards land on the right sector
    # while US "elementary"/"middle"/"high" cards land on theirs.
    if school_type:
        sector = resolve_primary_sector_for_school_type(country_code, school_type)
        if not sector:
            sector = _SCHOOL_TYPE_TO_PRIMARY_SECTOR.get(school_type, "")
        if sector:
            create_kwargs["primary_sector"] = sector[:64]
    school = School.objects.create(**create_kwargs)

    # A public-onboarding user who chose "We have no data to migrate" (a durable
    # WAIVE, distinct from "set up later" = defer) gets that recorded now that
    # the school exists. Best-effort; never blocks signup.
    from apps.schools.onboarding_waiver import waive_migration_if_flagged

    waive_migration_if_flagged(
        school, request.session.get("onboarding_migration_waived")
    )

    # v4.00.27 (2026-05-29) — persist all selected education cycles to the
    # School.education_system_types M2M so downstream blueprint/form/grade
    # band assignment can iterate every cycle the school covers, not just
    # the primary one. Falls open silently if registry isn't populated for
    # the picked codes — the singular school_type CharField still drives
    # the legacy primary_sector path so nothing breaks.
    if validated_types:
        try:
            from apps.registries.models import EducationSystemTypeRegistry
            for code in validated_types:
                try:
                    reg, _ = EducationSystemTypeRegistry.objects.get_or_create(
                        code=code[:64],
                        defaults={"name": code.replace("-", " ").title()[:128]},
                    )
                    school.education_system_types.add(reg)
                except (ValueError, TypeError):
                    continue
        except (ImportError, AttributeError) as exc:
            logger.debug(
                "signup education_system_types sync skipped err=%s",
                type(exc).__name__,
                exc_info=True,
            )
    _assign_data_residency_or_record_failure(school)
    try:
        from apps.lifecycle.unified_lifecycle import (
            CREATION_PATH_SELF_SERVE,
            set_creation_path,
        )

        set_creation_path(school, CREATION_PATH_SELF_SERVE)
    except (ImportError, ValueError, TypeError, OSError) as exc:
        # Lifecycle filter metadata only — non-blocking; log so operators
        # can still find the regression if it happens.
        logger.debug(
            "signup set_creation_path failed school_id=%s err=%s",
            school.id,
            type(exc).__name__,
            exc_info=True,
        )
    from datetime import timedelta

    expires_at = timezone.now() + timedelta(days=2)
    verification = SignupVerification.objects.create(
        school=school,
        email=email,
        expires_at=expires_at,
    )
    # 2026-06-06 — if this signup originated from an operator school-invite,
    # bind it now so the invite flips to "accepted" and the audit links the
    # invite → the created school. Best-effort; never blocks signup.
    _bind_tenant_invite_if_present(request, school)
    try:
        from apps.schools.funnel_events import record_marketing_funnel_event

        record_marketing_funnel_event("signup", request)
    except (ImportError, AttributeError, TypeError, ValueError) as exc:
        # Marketing funnel attribution only — non-blocking; log so a
        # missing-attribution regression is diagnosable.
        logger.warning(
            "signup record_marketing_funnel_event failed err=%s",
            type(exc).__name__,
            exc_info=True,
        )

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

    # The verification worker must not observe a school before its creation
    # transaction commits. This also prevents partial School rows when any
    # required verification/audit write fails above.
    transaction.on_commit(
        lambda: _send_signup_verification_email(request, verification)
    )

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
    # v4.00.98 Phase 5 — publish tenant.signup.created so the email matrix
    # fans out an operator alert + a tenant verification mail. Best-effort —
    # the signup view must never fail because the bus is slow.
    try:
        from apps.platform_runtime.event_bus import publish_event

        publish_event(
            "tenant.signup.created",
            {
                "school_id": str(getattr(school, "pk", "")),
                "school_name": name,
                "country_code": country_code,
                "subdomain": subdomain,
                "admin_email": email,
            },
            school_id=str(getattr(school, "pk", "")),
            strict_catalog=True,
            source="schools.signup_school",
        )
    except (ImportError, AttributeError, TypeError, ValueError, OSError, RuntimeError):
        logger.warning("signup_school_publish_event_failed", exc_info=True)

    return render(
        request,
        "schools/signup_school_done.html",
        {
            "email": email,
            "school_name": name,
            "workspace_url": workspace_url,
            "school_slug": slug,
            "migration_vendor": migration_vendor,
            "migration_domains": migration_domains,
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
    except (DatabaseError, ImportError, AttributeError, TypeError, ValueError):
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
            no_data = request.POST.get("no_data_to_migrate") in ("1", "true", "on")
            chosen_slug = (request.POST.get("vendor_slug") or "").strip().lower()
            chosen = resolve_vendor(chosen_slug) if chosen_slug else None
            # "No data to migrate" is a durable WAIVE, distinct from "set up
            # later" (a defer). Both clear the vendor; only no_data records a
            # durable migration waiver once the school exists (signup_school).
            session["onboarding_migration_waived"] = bool(no_data)
            if skip or no_data or not chosen:
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
    ob_country = session.get("onboarding_country_code") or ""
    from apps.siteconfig.signup_migration_recommendations import (
        migration_hint_for_country,
        order_onboarding_vendors,
    )
    from apps.siteconfig.signup_localization_bootstrap import signup_localization_json

    ob_pack = resolve_country_pack(ob_country) if ob_country else resolve_country_pack("US")
    ordered_vendors = order_onboarding_vendors(ONBOARDING_VENDORS, ob_country)
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
            "countries": countries,  # full ISO list — do NOT slice (the [:120] cap truncated at ~Kuwait)
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
            "onboarding_migration_waived": session.get(
                "onboarding_migration_waived", False
            ),
            "website_import_doc_url": "#",
            "onboarding_import_primary_color": session.get(
                "onboarding_import_primary_color"
            ),
            "onboarding_import_logo_url": session.get("onboarding_import_logo_url"),
            "onboarding_import_site_name": session.get("onboarding_import_site_name"),
            "onboarding_correlation_id": session.get("onboarding_correlation_id"),
            # v3.17 migration-step context
            "vendors": ordered_vendors,
            "migration_hint": migration_hint_for_country(ob_country),
            "signup_localization_json": signup_localization_json(
                request, ob_country or "US", ob_pack
            ),
            "selected_vendor": selected_vendor,
            "selected_vendor_slug": selected_vendor_slug,
            "data_domains": ONBOARDING_DATA_DOMAINS,
        },
    )


@require_GET
def _redirect_verified_admin_to_tenant_surface(request: HttpRequest, school, url_name: str):
    """After verify on the public host, send the admin to the tenant subdomain."""
    from apps.schools.provision_email_urls import school_subdomain_redirect_is_safe
    from apps.schools.tenant_url import build_tenant_backend_url

    if not school_subdomain_redirect_is_safe(school):
        return None

    try:
        path = reverse(url_name, urlconf="config.tenant_urls")
    except NoReverseMatch:
        try:
            path = reverse(url_name)
        except NoReverseMatch:
            return None
    return redirect(build_tenant_backend_url(request, school, path=path))


def _bind_tenant_invite_if_present(request: HttpRequest, school) -> None:
    """Mark an operator school-invite accepted when its recipient completes signup.

    Reads the invite token stashed in the session by :func:`accept_school_invite`,
    binds it to the freshly-created school, and emits ``tenant.invite.accepted``.
    Best-effort: a missing/expired invite (or any failure) never blocks signup.
    """
    token = (request.session.get("tenant_invite_token") or "").strip()
    if not token:
        return
    try:
        invite = TenantInvite.objects.filter(  # tenant-isolation-allow: public-invite-token-pre-tenant-signup
            token=token, accepted_at__isnull=True, revoked_at__isnull=True
        ).first()
    except (ValueError, TypeError):
        invite = None
    request.session.pop("tenant_invite_token", None)
    request.session.pop("tenant_invite_email", None)
    request.session.modified = True
    if invite is None:
        return
    invite.school = school
    invite.accepted_at = timezone.now()
    invite.save(update_fields=["school", "accepted_at"])
    logger.info(
        "tenant_invite_accepted invite=%s school_id=%s",
        invite.id,
        getattr(school, "pk", None),
    )


@never_cache
@require_GET
def accept_school_invite(request: HttpRequest):
    """Public landing for an operator-issued school invitation.

    Validates the token, stashes it in the session so ``signup_school`` can bind
    it on tenant creation, and routes the recipient into the standard guided
    onboarding/signup workflow. Invalid / expired / revoked / already-accepted
    invites get a friendly fallback that still links to self-signup.
    """
    token_str = (request.GET.get("token") or "").strip()
    invite = None
    if token_str:
        try:
            token_uuid = uuid.UUID(token_str)
        except (ValueError, TypeError):
            token_uuid = None
        if token_uuid is not None:
            invite = TenantInvite.objects.filter(  # tenant-isolation-allow: public-invite-token-pre-tenant-signup
                token=token_uuid
            ).first()
    if invite is None or not invite.is_pending:
        return render(
            request, "schools/accept_invite.html", {"invalid": True}, status=400
        )
    request.session["tenant_invite_token"] = str(invite.token)
    request.session["tenant_invite_email"] = invite.email
    request.session.modified = True
    return render(
        request,
        "schools/accept_invite.html",
        {
            "invite_email": invite.email,
            "invite_school_name": invite.school_name,
            "signup_url": reverse("signup_school"),
        },
    )


def _send_signup_verification_email(
    request: HttpRequest, verification, base_url: str = ""
) -> None:
    """Send (or re-send) the signup verification email for a SignupVerification.

    Centralized so the initial signup, the public resend endpoint, AND the
    operator console emit a byte-identical message through the canonical
    reliability-hardened sender. ``send_transactional`` never raises (returns a
    status dict) and async-dispatches the SMTP attempt on a daemon thread,
    writing an EmailDeliveryEvent audit row on completion — so a hung /
    misconfigured SMTP host can NEVER stall the request past the gateway
    timeout. The try/except only guards the synchronous envelope-construction
    path.

    ``base_url`` overrides the link host. When empty, the link always targets
    the public marketing host (``build_public_site_url``) — never the request
    host — so a mistaken manager-host signup still emits a clickable verify
    link. The operator console may pass ``base_url`` explicitly (same public
    origin).
    """
    school_name = getattr(verification.school, "name", "") or "your school"
    if base_url:
        verify_url = (
            f"{base_url.rstrip('/')}/verify-signup/?token={verification.token}"
        )
    else:
        from apps.schools.provision_email_urls import build_public_site_url

        verify_url = build_public_site_url(
            f"/verify-signup/?token={verification.token}"
        )
    subject = f"Verify your school: {school_name}"
    body = (
        f"Hello,\n\n"
        f"You requested to create a school on RunMyCampus: {school_name}.\n\n"
        f"Click the link below to verify your email and activate your school "
        f"(link valid for 2 days):\n\n"
        f"{verify_url}\n\n"
        f"If you did not request this, you can ignore this email.\n"
    )
    try:
        send_transactional(
            subject=subject,
            body=body,
            to=verification.email,
            from_email=settings.DEFAULT_FROM_EMAIL or "noreply@runmycampus.com",
            priority="transactional",
            async_send=True,
        )
    except (OSError, ConnectionError, ValueError, TypeError) as exc:
        logger.warning(
            "signup verification email sync raise err=%s school_id=%s",
            type(exc).__name__,
            getattr(verification.school, "id", None),
            exc_info=True,
        )


# Resend-verification abuse protection (cache-backed; sane defaults, overridable
# via settings). A per-email + per-IP cooldown blocks bursts; a per-email daily
# cap blocks slow-drip abuse. All gates fail OPEN to the generic success message
# so the endpoint never becomes an account-enumeration or timing oracle.
_RESEND_COOLDOWN_SECONDS = 120
_RESEND_DAILY_CAP = 5


def _resend_client_ip(request: HttpRequest) -> str:
    """Best-effort client IP for per-IP throttling (proxy-aware, first hop)."""
    xff = (request.META.get("HTTP_X_FORWARDED_FOR") or "").split(",")[0].strip()
    return xff or (request.META.get("REMOTE_ADDR") or "")


@never_cache
@require_http_methods(["GET", "POST"])
def resend_signup_verification(request: HttpRequest):
    """Re-send a signup verification email instead of forcing a fresh signup.

    A user whose 2-day verification link expired (or who never received it) can
    request a new one here — no need to re-run signup and collide with the
    half-created tenant. When a pending, unverified, not-yet-activated signup is
    found we ROTATE the token (so old links die) and extend the 2-day expiry,
    then re-send through the canonical sender.

    Enumeration-safe: the response is identical whether or not a matching signup
    exists. Abuse-protected by a per-email + per-IP cooldown and a per-email
    daily cap (both cache-backed and configurable).
    """
    generic_msg = (
        "If a pending school signup exists for that email and it hasn't been "
        "verified yet, we've sent a fresh verification link. Please check your "
        "inbox (and your spam folder)."
    )
    try:
        from apps.accounts.manager_login_next import request_is_manager_host
        from apps.schools.provision_email_urls import build_public_site_url

        if request_is_manager_host(request):
            return redirect(build_public_site_url(request.get_full_path()))
    except (ImportError, AttributeError, TypeError, ValueError):
        pass

    if request.method == "GET":
        return render(request, "schools/resend_verification.html", {})

    email = (request.POST.get("email") or "").strip().lower()
    if not email or "@" not in email or len(email) > 254:  # magic-number-allow: RFC 5321 max email length
        return render(
            request,
            "schools/resend_verification.html",
            {"error": "Please enter a valid email address."},
            status=400,
        )

    import hashlib

    from django.core.cache import cache

    cooldown_seconds = int(
        getattr(settings, "SIGNUP_RESEND_COOLDOWN_SECONDS", _RESEND_COOLDOWN_SECONDS)
    )
    daily_cap = int(getattr(settings, "SIGNUP_RESEND_DAILY_CAP", _RESEND_DAILY_CAP))

    email_key = hashlib.sha256(email.encode("utf-8")).hexdigest()[:24]
    ip = _resend_client_ip(request)
    ip_key = hashlib.sha256(ip.encode("utf-8")).hexdigest()[:24] if ip else "noip"
    cooldown_key = f"resend_verify_cd:{email_key}"
    ip_cooldown_key = f"resend_verify_ipcd:{ip_key}"
    daily_key = f"resend_verify_day:{email_key}"

    throttled = (
        cache.get(cooldown_key) is not None
        or cache.get(ip_cooldown_key) is not None
        or (cache.get(daily_key) or 0) >= daily_cap
    )
    if throttled:
        # Same generic response on throttle — keeps the endpoint
        # enumeration-safe and prevents it from becoming a timing oracle.
        return render(
            request,
            "schools/resend_verification.html",
            {"sent": True, "message": generic_msg},
        )

    # Arm the cooldowns BEFORE any work so a burst of concurrent posts can't
    # each fire a send.
    cache.set(cooldown_key, 1, cooldown_seconds)
    if ip:
        cache.set(ip_cooldown_key, 1, cooldown_seconds)
    try:
        cache.incr(daily_key)
    except ValueError:
        cache.set(daily_key, 1, 24 * 60 * 60)

    verification = (
        # tenant-isolation-allow: public-signup-verification-keyed-by-unique-email-not-tenant-scoped
        SignupVerification.objects.filter(
            email__iexact=email,
            verified_at__isnull=True,
            school__is_active=False,
        )
        .select_related("school")
        .order_by("-created_at")
        .first()
    )
    if verification is not None:
        # Rotate the token so any previously-mailed (possibly leaked) link dies,
        # and refresh the 2-day window.
        verification.token = uuid.uuid4()
        verification.expires_at = timezone.now() + timedelta(days=2)
        verification.save(update_fields=["token", "expires_at"])
        _send_signup_verification_email(request, verification)
        logger.info(
            "resend_signup_verification sent school_id=%s",
            getattr(verification.school, "id", None),
        )

    return render(
        request,
        "schools/resend_verification.html",
        {"sent": True, "message": generic_msg},
    )


def _verify_signup_retryable_unavailable(request: HttpRequest):
    """503 when Postgres blips mid-verification so the magic link can be retried."""
    response = render(
        request,
        "schools/verify_signup.html",
        {
            "error": (
                "Our servers are briefly unavailable. "
                "Please wait a moment and open your verification link again."
            ),
        },
        status=503,
    )
    response["Retry-After"] = "30"
    return response


def verify_signup(request: HttpRequest):
    """
    GET ?token=xxx: look up SignupVerification, run provisioning, mark
    verification used, redirect into the public-host onboarding wizard.

    v4.00.98 fix: do NOT set ``school.is_active = True`` before dispatching
    provisioning.  ``_do_provision`` short-circuits on ``school.is_active``
    (treating it as "already fully provisioned, skip re-doing it"), and the
    activation here was making it skip the welcome-email step at the end of
    provisioning — so verified users never received the welcome email.
    Activation now happens inside ``_do_provision`` (tasks.py) right before
    the welcome email send, restoring the original contract.
    """
    from apps.platform_runtime.transient_db import (
        is_transient_database_error,
        reset_broken_database_state,
    )

    # Signup verify is public-host only; manager links must bounce to runmycampus.com.
    try:
        from apps.accounts.manager_login_next import request_is_manager_host
        from apps.schools.provision_email_urls import build_public_site_url

        if request_is_manager_host(request):
            return redirect(build_public_site_url(request.get_full_path()))
    except (ImportError, AttributeError, TypeError, ValueError):
        pass

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

    try:
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
    except (DatabaseError, TransactionManagementError) as exc:
        reset_broken_database_state()
        if isinstance(exc, TransactionManagementError) or is_transient_database_error(exc):
            logger.warning("verify_signup_lookup_transient_db: %s", exc)
            return _verify_signup_retryable_unavailable(request)
        raise

    if not verification:
        return render(
            request,
            "schools/verify_signup.html",
            {"error": "Link expired or already used."},
            status=400,
        )

    school = verification.school
    # v4.00.98 fix: do NOT activate the school here — provisioning sets
    # school.is_active=True at its successful tail (apps/schools/tasks.py
    # _do_provision).  Premature activation here caused _do_provision to
    # short-circuit and skip the welcome email send.
    verification.verified_at = timezone.now()
    try:
        verification.save(update_fields=["verified_at"])
    except (DatabaseError, TransactionManagementError) as exc:
        reset_broken_database_state()
        if isinstance(exc, TransactionManagementError) or is_transient_database_error(exc):
            logger.warning("verify_signup_save_transient_db: %s", exc)
            return _verify_signup_retryable_unavailable(request)
        raise
    try:
        # Both funnel helpers are intentionally best-effort and one of them
        # catches DatabaseError internally. Give the optional writes their own
        # savepoint so a swallowed SQL failure cannot poison the surrounding
        # signup transaction and make the required owner/provisioning queries
        # fail with TransactionManagementError (or a closed SQLite connection).
        with transaction.atomic():
            from apps.schools.funnel_events import (
                record_marketing_funnel_event,
                record_school_funnel_once,
            )

            record_school_funnel_once("signup_completed", school, request)
            record_marketing_funnel_event("activation", request, school=school)
    except (ImportError, AttributeError, TypeError, ValueError, DatabaseError):
        logger.warning(
            "verify_signup_optional_funnel_event_failed",
            exc_info=True,
        )

    # v3.58.x Wave 9 Agent K — route provisioning through the canonical
    # ``dispatch_provision_school`` so it queues via Celery when the
    # broker is reachable (returning immediately to the operator) and
    # falls back to synchronous-in-request only when Celery is fully
    # unavailable. The sync fallback was the v3.57 status quo from
    # this view and is preserved as a last resort — but on Render +
    # other PaaS deployments where Celery + Redis broker are wired up,
    # the verify-link click will now return in well under a second.
    # v4.00.2 audit (2026-05-28): the previous bare ``pass`` silently
    # swallowed any provisioning dispatch failure, leaving the user logged
    # in with a half-provisioned school AND no welcome email — operators
    # had no signal anything went wrong. Log + record a provisioning event
    # so the offboarding queue / timeline surfaces the failure. The user
    # is still logged in (auth on success was already proven by email
    # verification), but the timeline now reflects reality.
    #
    # 2026-06-08 fix (onboarding dead-end): provisioning now runs BEFORE the
    # welcome email + redirect so the freshly-created admin user exists and we
    # can hand the new owner a token-authed "set your password" link. The token
    # is the auth, so it survives the public→tenant host hop where a session
    # cookie would not — closing the bug where verify dumped owners on a login
    # page their passwordless account could never satisfy.
    # Create the owner account up-front (idempotent), BEFORE dispatching
    # provisioning. On a broker-backed deploy provisioning is queued on a Celery
    # worker that hasn't run yet, so without this the owner row wouldn't exist
    # when we build the onboarding link below → ``admin_user`` would be None →
    # the new owner is dumped on the login page instead of the guided wizard
    # (the exact dead-end this flow removes). The provisioning task reuses this
    # same row. (2026-06-08: this is why it worked in dev — broker-less = sync
    # provisioning created the user in-request — but failed in prod.)
    try:
        from apps.schools.tasks import ensure_admin_user_for_school

        ensure_admin_user_for_school(school, verification.email)
    except (DatabaseError, TransactionManagementError) as exc:
        reset_broken_database_state()
        if isinstance(exc, TransactionManagementError) or is_transient_database_error(exc):
            logger.warning("verify_signup_ensure_admin_transient_db: %s", exc)
            return _verify_signup_retryable_unavailable(request)
        raise
    except (ImportError, AttributeError, TypeError, ValueError, IntegrityError) as exc:
        logger.warning("verify_signup_ensure_admin_user_failed", exc_info=True)
        try:
            from apps.schools.models import SchoolProvisioningEvent

            SchoolProvisioningEvent.log_event(
                school=school,
                event_type=SchoolProvisioningEvent.EventType.FAILED,
                status=SchoolProvisioningEvent.Status.ERROR,
                message="Bootstrap owner account could not be created after verification",
                payload={"error_type": type(exc).__name__, "error": str(exc)[:500]},
            )
        except (ImportError, AttributeError, TypeError, ValueError, OSError):
            pass

    try:
        from apps.schools.tasks import kick_complete_provisioning_background

        # Kick provisioning in the BACKGROUND and return FAST — never block the
        # verify request on full provisioning. Blocking risks gateway timeouts/502
        # on a slow provision AND hides the live progress the owner should watch.
        # The owner row was already created above (ensure_admin_user_for_school),
        # so the lookup below is safe regardless of the background job's timing.
        # The owner is redirected into the onboarding launchpad, which polls
        # ``resolve_provisioning_progress`` and renders a real-time, step-by-step
        # progress bar + a final summary report. Reliability is guaranteed by the
        # progress poll endpoint's watchdog (it auto-kicks a stalled job), so
        # provisioning always finishes — no "school never finishes provisioning".
        # This dispatches to Celery when a broker is available AND runs a
        # daemon-thread completion as a booster/fallback (covers the broker-less
        # and queued-but-unconsumed cases).
        kick_complete_provisioning_background(
            str(school.id), contact_email=verification.email,
        )
    except Exception as exc:  # noqa: BLE001 — provisioning must NEVER 500 the verify page; degrade to onboarding + retry
        logger.warning(
            "signup verify dispatch_provision_school failed school_id=%s err=%s",
            school.id,
            type(exc).__name__,
            exc_info=True,
        )
        try:
            from apps.schools.tasks import complete_provisioning_for_school

            complete_provisioning_for_school(
                str(school.id), contact_email=verification.email
            )
        except (
            ImportError,
            AttributeError,
            TypeError,
            ValueError,
            OSError,
            RuntimeError,
        ) as sync_exc:
            logger.warning(
                "signup verify complete_provisioning fallback failed school_id=%s err=%s",
                school.id,
                type(sync_exc).__name__,
                exc_info=True,
            )
        try:
            from apps.schools.models import SchoolProvisioningEvent

            SchoolProvisioningEvent.log_event(
                school=school,
                event_type=SchoolProvisioningEvent.EventType.FAILED,
                status=SchoolProvisioningEvent.Status.ERROR,
                message="Provisioning dispatch failed after signup verification",
                payload={"error_type": type(exc).__name__, "error": str(exc)[:500]},
            )
        except (ImportError, AttributeError, TypeError, ValueError, OSError):
            pass

    # Resolve the freshly-provisioned admin user. Synchronous provisioning
    # creates it in-request; an async/Celery dispatch may not have created it
    # yet → ``admin_user`` stays None and we degrade gracefully below.
    User = get_user_model()
    try:
        admin_user = (
            User.objects.filter(email__iexact=verification.email).order_by("id").first()
        )
    except (DatabaseError, TransactionManagementError) as exc:
        reset_broken_database_state()
        if isinstance(exc, TransactionManagementError) or is_transient_database_error(exc):
            logger.warning("verify_signup_admin_lookup_transient_db: %s", exc)
            return _verify_signup_retryable_unavailable(request)
        raise

    # Build the one-time onboarding link (token-authed; host-independent). It
    # opens the guided first-run wizard — a welcoming "create your account"
    # step (password + name) → school setup → launchpad — instead of dropping
    # the new owner on a bare set-password/login page that reads as "you already
    # have an account". The signed token is the auth, so it survives the
    # public→tenant host hop.
    setup_password_url = ""
    if admin_user is not None:
        try:
            from apps.schools.provision_email_urls import build_owner_onboarding_url

            setup_password_url = build_owner_onboarding_url(school, admin_user)
        except (ImportError, AttributeError, TypeError, ValueError):
            setup_password_url = ""

    # Welcome email is sent once from ``_do_provision`` after the school is active
    # (``send_welcome_email`` → public-host onboarding URL). Do NOT publish
    # ``tenant.signup.completed`` here: that fired the matrix welcome email
    # prematurely (before provisioning) and duplicated ``send_welcome_email``.

    # Magic-link login — verifying the email proves ownership, so log the
    # newly-provisioned admin in directly. Falls back to the legacy login
    # redirect when the admin user cannot be resolved.
    if admin_user is not None and admin_user.is_active:
        try:
            # Must name a backend explicitly: with multiple AUTHENTICATION_BACKENDS
            # configured, Django's login() raises ValueError unless told which one
            # authed this user. ``admin_user`` is a plain ORM fetch (no ``.backend``
            # attr), so without this the ValueError was swallowed below → the
            # onboarding redirect (further down) was skipped and the new owner was
            # dumped on the login wall — the exact dead-end this flow removes.
            auth_login(
                request,
                admin_user,
                backend="django.contrib.auth.backends.ModelBackend",
            )
        except (ValueError, TypeError, AttributeError):
            admin_user = None

    if admin_user is not None and admin_user.is_active:
        try:
            from apps.lifecycle.tenant_school_resolve import bind_lifecycle_school_session

            bind_lifecycle_school_session(request, school)
        except ImportError:
            pass
        request.session["signup_school_id"] = str(school.pk)
        request.session.modified = True
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
        try:
            from apps.lifecycle.unified_lifecycle import (
                STATE_PROVISIONING,
                record_unified_transition,
            )

            record_unified_transition(
                school,
                STATE_PROVISIONING,
                actor=admin_user,
                note="signup_verified",
            )
        except (ImportError, ValueError, TypeError, OSError):
            pass
        # Send the new owner straight into the guided onboarding wizard (set
        # password + name → school → done) as a RELATIVE redirect, so it stays
        # on the host the verify link was on (the public site, which ALWAYS
        # resolves). Do NOT redirect to the absolute tenant-subdomain URL here:
        # on the async/prod path the subdomain isn't live until the Celery
        # worker flips school.is_active, so it would bounce to school-not-found
        # → /activation/first-action/ → MFA → the manager login wall (the exact
        # 10x-reported dead-end). The onboarding prefix is allowlisted in the
        # conversion lock + MFA bypass so the wizard can't be ejected mid-setup.
        # The welcome email keeps the absolute tenant link for later (post-activation).
        onboarding_path = ""
        try:
            from apps.schools.provision_email_urls import build_owner_onboarding_path

            onboarding_path = build_owner_onboarding_path(admin_user)
        except (ImportError, AttributeError, TypeError, ValueError):
            onboarding_path = ""
        if onboarding_path:
            return redirect(onboarding_path)
        # Fallback: absolute tenant onboarding URL (resolves once tenant is live).
        if setup_password_url:
            return redirect(setup_password_url)

        # Fallback (no setup URL resolvable): original tenant-surface chain.
        for url_name in (
            "tenant_provisioning_status",
            "school_studio",
            "studio_os:launch",
            "accounts:backend_dashboard",
        ):
            target = _redirect_verified_admin_to_tenant_surface(
                request, school, url_name
            )
            if target is not None:
                return target
        return redirect("/")

    # No admin user resolved (async provisioning still running): a passwordless
    # account can't satisfy the login page — show a recovery screen instead.
    return render(
        request,
        "schools/verify_signup.html",
        {
            "error": (
                "We verified your email but could not finish account setup yet. "
                "Please wait a moment and open the link again, or resend a fresh link."
            ),
        },
        status=503,
    )


@require_POST
def api_trial_school(request: HttpRequest):
    """
    W1-2: Self-service trial API. POST JSON: name, contact_email, country_code (optional).
    Creates school with billing_type=FREE_TRIAL, trial_end_date=now+owner_free_trial_days()
    (approved default 30d, env-tunable), enqueues provisioning.
    Returns 202 with school_id, job_id, message "We'll email when ready".
    """
    # Abuse defense: this is fully unauthenticated and creates a tenant + sends
    # mail, so throttle per IP (separate bucket from the HTML signup form).
    throttled = _signup_rate_limited_response(
        request, "api_trial_school", json_response=True
    )
    if throttled is not None:
        return throttled

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

    # Reverse-trial length (approved default 30 days; env-tunable). See
    # apps/schools/plan_gating.py::owner_free_trial_days.
    from apps.schools.plan_gating import owner_free_trial_days

    trial_end = (timezone.now() + timedelta(days=owner_free_trial_days())).date()
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
    try:
        from apps.lifecycle.unified_lifecycle import (
            CREATION_PATH_SELF_SERVE,
            set_creation_path,
        )

        set_creation_path(school, CREATION_PATH_SELF_SERVE)
    except (ImportError, ValueError, TypeError, OSError):
        pass
    if default_region:
        school.settings = school.settings or {}
        school.settings["country_code"] = country_code
        school.save(update_fields=["settings"])
        try:
            from apps.policies.policy_registry import invalidate_policy_cache

            invalidate_policy_cache(school)
        except (ImportError, AttributeError, TypeError, ValueError):
            pass

    from apps.schools.tasks import complete_provisioning_for_school
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
    dispatch = complete_provisioning_for_school(
        str(school.id), contact_email=contact_email
    )
    school.refresh_from_db(fields=["is_active"])
    job_id = dispatch.get("job_id")
    payload = {"job_id": job_id or "", "is_active": bool(getattr(school, "is_active", False))}
    if dispatch.get("fallback") and dispatch.get("reason"):
        payload["fallback_reason"] = dispatch["reason"]
    if dispatch.get("sync_completed"):
        payload["sync_completed"] = True
    SchoolProvisioningEvent.log_event(
        school=school,
        event_type=(
            SchoolProvisioningEvent.EventType.COMPLETED
            if getattr(school, "is_active", False)
            else SchoolProvisioningEvent.EventType.QUEUED
        ),
        status=SchoolProvisioningEvent.Status.INFO,
        message=(
            "Trial provisioning completed."
            if getattr(school, "is_active", False)
            else (dispatch.get("message") or "Provisioning queued.")
        ),
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
    """Locate the school for a post-signup admin (public host or tenant host)."""
    try:
        from apps.lifecycle.tenant_school_resolve import resolve_request_school

        return resolve_request_school(request)
    except ImportError:
        return getattr(request, "school", None)


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


# Words that describe the *kind* of school — handy as an optional suffix but
# rarely the memorable part of a web address on their own.
_SLUG_TYPE_WORDS = (
    "school",
    "schools",
    "academy",
    "academies",
    "college",
    "institute",
    "institution",
    "university",
    "prep",
    "preparatory",
    "montessori",
    "grammar",
    "seminary",
    "polytechnic",
)
# Connector / filler words dropped when choosing the anchor.
_SLUG_STOPWORDS = (
    "the",
    "of",
    "and",
    "for",
    "a",
    "an",
    "at",
    "in",
    "on",
    "de",
    "la",
    "el",
)
# Long descriptor words shortened into a tidier variant.
_SLUG_ABBREV = {
    "international": "intl",
    "elementary": "elem",
    "secondary": "sec",
    "primary": "prim",
    "junior": "jr",
    "senior": "sr",
    "incorporated": "inc",
    "community": "comm",
    "technology": "tech",
    "technical": "tech",
}
_SLUG_SUGGEST_MIN = 3
_SLUG_SUGGEST_MAX = 120


def build_slug_suggestions(name: str, country_code: str = "") -> list[str]:
    """Creative, memorable web-address candidates derived from a school name.

    "Smart & short": lead with the most memorable anchor word, then a few
    clean variants (anchor+type, compact, abbreviated descriptor, optional
    country tag), and finally the full verbatim slug as a familiar fallback.

    Pure string logic — NO database access — so it is cheap, deterministic and
    unit-testable. Returns an ORDERED, de-duplicated list of valid slug strings
    (best/shortest first); the caller layers availability on top.
    """
    from django.utils.text import slugify as _dj_slugify

    full = _dj_slugify(name or "")[:_SLUG_SUGGEST_MAX]
    tokens = [t for t in full.split("-") if t]
    if not tokens:
        return []

    significant = [
        t
        for t in tokens
        if t not in _SLUG_STOPWORDS and t not in _SLUG_TYPE_WORDS
    ]
    type_word = next((t for t in tokens if t in _SLUG_TYPE_WORDS), "")

    # Anchor: keep a leading "st"/"saint" glued to the next word (st-marys),
    # otherwise the first meaningful word is the most memorable handle.
    if significant:
        if significant[0] in ("st", "saint") and len(significant) > 1:
            anchor = "st-" + significant[1]
            second = significant[2] if len(significant) > 2 else ""
        else:
            anchor = significant[0]
            second = significant[1] if len(significant) > 1 else ""
    else:
        anchor = tokens[0]
        second = tokens[1] if len(tokens) > 1 else ""

    ordered: list[str] = []

    def _add(candidate: str) -> None:
        cand = _dj_slugify(candidate or "")[:_SLUG_SUGGEST_MAX]
        if (
            _SLUG_SUGGEST_MIN <= len(cand)
            and cand not in _RESERVED_SLUGS
            and cand not in ordered
        ):
            ordered.append(cand)

    _add(anchor)  # greenfield
    if type_word:
        _add(f"{anchor}-{type_word}")  # greenfield-academy
        _add(f"{anchor}{type_word}")  # greenfieldacademy
    if second:
        _add(f"{anchor}-{_SLUG_ABBREV.get(second, second)}")  # greenfield-intl
        _add(f"{anchor}-{second}")  # greenfield-international
    cc = (country_code or "").strip().lower()
    if len(cc) == 2 and cc.isalpha():
        _add(f"{anchor}-{cc}")  # greenfield-ke
    _add(full)  # greenfield-international-academy (familiar fallback)
    return ordered


@never_cache
@require_GET
@ratelimit(key="ip", rate="60/m", method="GET", block=True)
def signup_slug_suggest(request: HttpRequest) -> JsonResponse:
    """Live web-address suggestions from a school NAME (as the operator types).

    Query params:
        name         – the school name (required for a meaningful answer)
        country_code – optional 2-letter ISO code; adds a country-tagged option

    Response shape:
        {
          "name": <echoed>,
          "suggestions": [{"slug": <str>, "available": <bool>}, ...]  # up to 4
        }

    Suggestion *generation* is DB-free; only a bounded number of availability
    probes run (mirrors signup_slug_check's cost profile and 60/min/IP limit),
    so the front door never becomes a query amplifier under shared-NAT load.
    """
    name = (request.GET.get("name") or "").strip()[:200]  # magic-number-allow: school-name-input-cap
    country_code = (request.GET.get("country_code") or "").strip()[:2]
    candidates = build_slug_suggestions(name, country_code)[:6]

    results = []
    for slug in candidates:
        # tenant-isolation-allow: public-slug-availability-lookup-no-tenant-scope
        taken = (
            School.objects.filter(slug=slug).exists()
            # tenant-isolation-allow: public-slug-availability-lookup-no-tenant-scope
            or School.objects.filter(subdomain=slug).exists()
        )
        results.append({"slug": slug, "available": not taken})

    # Surface available options first while preserving generation order within
    # each group (Python's sort is stable) — the cleanest free slug leads.
    results.sort(key=lambda item: not item["available"])
    return JsonResponse({"name": name, "suggestions": results[:4]})


@require_GET
@ratelimit(key="ip", rate="120/m", method="GET", block=True)
def signup_decisions_preview(request: HttpRequest) -> JsonResponse:
    """Live progressive decision model for the setup step (recommended flags).

    Recomputes, from the SAME deterministic engine the page server-renders,
    which option is recommended for each configuration decision, which
    decisions the answers-so-far already settle (auto-applied, not asked), and
    which no longer apply. The signup form calls this as earlier answers change
    (country, cycles, school model, campuses) so the "Recommended" badges and
    pre-selection track the operator's input without re-loading the page.

    Read-only and DB-free by design: idempotent GET (no CSRF), no tenant scope
    (public onboarding), and no external / AI call — the flags are identical on
    the edge and in the cloud. Rate-limited like the sibling slug endpoints so
    the front door never becomes a compute amplifier under shared-NAT load.
    """
    from apps.schools.onboarding_decisions import build_onboarding_decisions

    country_code = (
        request.GET.get("country_code") or request.GET.get("country") or ""
    ).strip()[:2]
    funding = (
        request.GET.get("funding") or request.GET.get("funding_type") or ""
    ).strip().lower()[:24]
    cycles_raw = (request.GET.get("cycles") or "").strip()
    cycles = [
        token.strip().lower()
        for token in cycles_raw.replace("|", ",").split(",")
        if token.strip()
    ][:12]
    try:
        campus_count = min(10_000, max(0, int(request.GET.get("campus_count") or 0)))
    except (TypeError, ValueError):
        campus_count = 0
    # Region key sharpens connectivity/governance defaults when the specific
    # country code is unlisted. Resolved in-memory from the country pack, never
    # from the DB, so this stays a zero-query endpoint.
    region_key = (request.GET.get("region") or "").strip().lower()[:48]
    if not region_key and country_code:
        try:
            from apps.siteconfig.country_localization_service import resolve_country_pack

            source = str(resolve_country_pack(country_code).get("_source") or "")
            if source.startswith("regional:"):
                region_key = source.split(":", 1)[1]
        except Exception:  # pragma: no cover - defensive; pack resolution is best-effort
            region_key = ""

    model = build_onboarding_decisions(
        country_code=country_code,
        region_key=region_key,
        education_cycles=cycles,
        funding_type=funding,
        institution_profile={"campus_count": campus_count},
    )
    return JsonResponse(model)


@require_GET
@ratelimit(key="ip", rate="90/m", method="GET", block=True)
def signup_recommendations_preview(request: HttpRequest) -> JsonResponse:
    """Return the canonical explainable recommendation preview.

    This endpoint intentionally calls the same deterministic engine persisted
    at signup.  It is DB-free, AI-free and safe for local-first clients to
    cache.  The response distinguishes evidence readiness from statistical
    probability so the UI cannot manufacture a high-confidence claim.
    """

    from apps.schools.onboarding_recommendations import (
        build_onboarding_recommendations,
    )

    def values(name: str, *, limit: int = 24) -> list[str]:
        raw = request.GET.getlist(name)
        if len(raw) == 1 and "," in raw[0]:
            raw = raw[0].split(",")
        return [str(value).strip().lower()[:64] for value in raw if str(value).strip()][
            :limit
        ]

    profile_keys = (
        "organization_scope",
        "learner_scale",
        "operating_model",
        "connectivity_profile",
        "funding_type",
        "session_pattern",
        "curriculum_board",
        "governance_profile",
        "payment_profile",
        "assessment_profile",
        "identity_profile",
        "data_residency_requirement",
        "accessibility_profile",
        "migration_complexity",
        "automation_preference",
        "lms_preference",
        "migration_vendor",
    )
    profile = {
        key: (request.GET.get(key) or "").strip()[:128]
        for key in profile_keys
        if request.GET.get(key) not in (None, "")
    }
    for key in ("student_capacity", "campus_count", "staff_count"):
        raw = (request.GET.get(key) or "").strip()
        if raw:
            try:
                profile[key] = min(1_000_000, max(0, int(raw)))
            except ValueError:
                profile[key] = 0
    profile["operational_services"] = values("operational_services")
    profile["migration_domains"] = values("migration_domains")
    manifest = build_onboarding_recommendations(
        country_code=(request.GET.get("country_code") or "").strip()[:2],
        education_cycles=values("school_type"),
        language_codes=values("language_codes"),
        institution_profile=profile,
    )
    response = JsonResponse(
        {
            "ok": True,
            "engine": manifest["engine"],
            "version": manifest["version"],
            "fingerprint": manifest["fingerprint"],
            "confidence": manifest["confidence_envelope"],
            "recommendations": manifest["recommendations"],
            "cards": manifest["recommendation_cards"],
            "missing_inputs": manifest["missing_inputs"],
            "validation_issues": manifest["validation_issues"],
            "review_state": manifest["review_state"],
        }
    )
    response["Cache-Control"] = "private, max-age=60"
    return response


@require_http_methods(["POST"])
@ratelimit(key="ip", rate="60/m", method="POST", block=True)
def signup_journey_event(request: HttpRequest) -> JsonResponse:
    """Record a privacy-minimized signup journey event.

    Only a bounded stage number and categorical action are accepted. No form
    value, school name, email, free text or recommendation payload crosses this
    endpoint.
    """

    try:
        stage = int(request.POST.get("stage") or 0)
    except (TypeError, ValueError):
        stage = 0
    action = (request.POST.get("action") or "").strip().lower()
    if stage not in range(1, 6) or action not in {
        "view",
        "continue",
        "back",
        "offline-save",
        "offline-recovered",
        "submit-queued",
    }:
        return JsonResponse({"ok": False, "error": "invalid_event"}, status=400)
    from apps.schools.funnel_events import record_marketing_funnel_event

    record_marketing_funnel_event(
        "signup_started",
        request,
        metadata={"journey_version": 4, "stage": stage, "action": action},
    )
    return JsonResponse({"ok": True}, status=202)
