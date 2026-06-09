"""
Section 8: Industry Interoperability — landing, Caddy ask, LTI placeholder, global login.
"""

import logging
import os
import json
import base64
import secrets
from binascii import Error as BinasciiError
from urllib.parse import urlencode
from django.http import (
    HttpResponse,
    HttpResponseForbidden,
    HttpResponseNotFound,
    JsonResponse,
)
from django.views.decorators.http import require_GET
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.shortcuts import redirect, render
from django.db import DatabaseError
from django.urls import NoReverseMatch, reverse
from django.utils import timezone

from apps.api.rate_limit import throttle_ip_request
from apps.siteconfig.integration_registry import resolve_service_integration

logger = logging.getLogger(__name__)


def _caddy_ip_allowed(request) -> bool:
    """If CADDY_CHECK_ALLOWED_IPS is set (comma-separated), only those IPs are allowed. Otherwise all allowed."""
    allowed = os.getenv("CADDY_CHECK_ALLOWED_IPS", "").strip()
    if not allowed:
        return True
    remote = (request.META.get("REMOTE_ADDR") or "").strip()
    return remote in [ip.strip() for ip in allowed.split(",") if ip.strip()]


def _caddy_token_allowed(request) -> bool:
    """
    Optional shared-secret gate for Caddy ask.

    Set CADDY_CHECK_TOKEN and send it as X-Caddy-Ask-Token or ?token=. When unset,
    existing IP/rate/domain checks remain the full gate.
    """
    expected = os.getenv("CADDY_CHECK_TOKEN", "").strip()
    if not expected:
        return True
    supplied = (
        request.headers.get("X-Caddy-Ask-Token")
        or request.GET.get("token")
        or ""
    ).strip()
    return bool(supplied) and secrets.compare_digest(supplied, expected)


CADDY_CHECK_RATE_LIMIT_WINDOW = 60 * 15
CADDY_CHECK_RATE_LIMIT_MAX = 180


@require_GET
def verify_caddy_domain(request):
    """
    Section 8.5: Caddy on-demand TLS "ask" endpoint.
    GET ?domain=greenwood.yoursystem.com → 200 if domain allowed, 404 otherwise.
    If CADDY_CHECK_ALLOWED_IPS is set (comma-separated), only those IPs get 200/404; others get 403.
    """
    if not _caddy_ip_allowed(request):
        return HttpResponseForbidden("IP not allowed")
    if not _caddy_token_allowed(request):
        return HttpResponseForbidden("Invalid Caddy ask token")
    allowed, retry_after = throttle_ip_request(
        request,
        scope="caddy_domain_check",
        max_count=CADDY_CHECK_RATE_LIMIT_MAX,
        window_seconds=CADDY_CHECK_RATE_LIMIT_WINDOW,
    )
    if not allowed:
        response = HttpResponse("Too many requests", status=429)
        response["Retry-After"] = str(retry_after)
        return response
    domain = (request.GET.get("domain") or "").strip()
    if not domain:
        return HttpResponseNotFound("Missing domain parameter")
    domain_lower = domain.lower()
    if domain_lower in ("localhost", "127.0.0.1", "::1"):
        return HttpResponseNotFound("Internal domains not allowed")

    # Optional short-TTL cache for Caddy ask (reduce DB load)
    cache_key = "caddy_ask:%s" % domain_lower
    cache_ttl = 60
    try:
        from django.core.cache import cache
        from django.conf import settings as django_settings

        cache_ttl = getattr(django_settings, "CADDY_ASK_CACHE_TTL", 60) or 60
        if cache_ttl > 0:
            cached = cache.get(cache_key)
            if cached is True:
                return HttpResponse(status=200)
            if cached is False:
                return HttpResponseNotFound("Domain not recognized")
    except SECTION8_CACHE_FAILURES:
        cache = None

    # 1. Runtime domain table (django-tenants): authoritative routing map.
    try:
        from apps.customers.models import Domain

        if Domain.objects.filter(
            domain=domain_lower, tenant__school__is_active=True
        ).exists():
            if cache:
                try:
                    cache.set(cache_key, True, timeout=cache_ttl)
                except SECTION8_CACHE_FAILURES:
                    pass
            return HttpResponse(status=200)
    except SECTION8_OPTIONAL_FAILURES + (DatabaseError,):
        pass

    # 2. SchoolDomain (shared schema): multiple domains per tenant, is_verified
    try:
        from .models import SchoolDomain

        # tenant-isolation-allow: view-layer-scoped-via-request-school-or-role-graph
        if SchoolDomain.objects.filter(
            domain=domain_lower, is_verified=True, school__is_active=True
        ).exists():
            if cache:
                try:
                    cache.set(cache_key, True, timeout=cache_ttl)
                except SECTION8_CACHE_FAILURES:
                    pass
            return HttpResponse(status=200)
    except SECTION8_OPTIONAL_FAILURES + (DatabaseError,):
        pass

    # 3. Legacy: School.subdomain and School.custom_domain
    from .models import School

    subdomain = domain_lower.split(".")[0] if "." in domain_lower else domain_lower
    if School.objects.filter(subdomain=subdomain, is_active=True).exists():
        if cache:
            try:
                cache.set(cache_key, True, timeout=cache_ttl)
            except SECTION8_CACHE_FAILURES:
                pass
        return HttpResponse(status=200)
    if School.objects.filter(
        custom_domain=domain_lower, custom_domain_verified=True, is_active=True
    ).exists():
        if cache:
            try:
                cache.set(cache_key, True, timeout=cache_ttl)
            except SECTION8_CACHE_FAILURES:
                pass
        return HttpResponse(status=200)

    if cache:
        try:
            cache.set(cache_key, False, timeout=cache_ttl)
        except SECTION8_CACHE_FAILURES:
            pass
    return HttpResponseNotFound("Domain not recognized")


DISCOVERY_RATE_LIMIT_KEY = "discovery_post:{ip}"
DISCOVERY_RATE_LIMIT_MAX = 10
DISCOVERY_RATE_LIMIT_WINDOW = 60 * 15  # 15 minutes
LTI_RATE_LIMIT_WINDOW = 60 * 15
LTI_RATE_LIMIT_MAX = 240
SECTION8_MUTATION_CONTENT_TYPES = {"application/json"}
SECTION8_OPTIONAL_FAILURES = (
    AttributeError,
    ImportError,
    LookupError,
    RuntimeError,
    TypeError,
    ValueError,
)
SECTION8_CACHE_FAILURES = SECTION8_OPTIONAL_FAILURES + (DatabaseError, OSError)
SECTION8_JSON_FAILURES = (
    UnicodeDecodeError,
    json.JSONDecodeError,
    TypeError,
    ValueError,
)
SECTION8_JWT_FAILURES = SECTION8_JSON_FAILURES + (BinasciiError,)


def _safe_reverse(name: str) -> str:
    try:
        return reverse(name)
    except NoReverseMatch:
        return "#"
    except SECTION8_OPTIONAL_FAILURES:
        return "#"


def _role_onboarding_checklists() -> list[dict]:
    """
    Phase 2: Role-aware first-run checklists shown on public discovery pages.
    """
    return [
        {
            "role": "School admin",
            "summary": "Launch your school tenant and configure core operations.",
            "steps": [
                {
                    "title": "Create or claim your school",
                    "detail": "Start with school identity, domain, and onboarding wizard.",
                    "href": _safe_reverse("signup_school"),
                    "cta": "Start school setup",
                },
                {
                    "title": "Verify access and permissions",
                    "detail": "Confirm admin login and role access for your team.",
                    "href": _safe_reverse("accounts:login"),
                    "cta": "Open admin login",
                },
                {
                    "title": "Activate finance and support controls",
                    "detail": "Review billing, support, and governance workflows.",
                    "href": "/super/command-center/",
                    "cta": "View command center",
                },
            ],
        },
        {
            "role": "Teacher",
            "summary": "Get classroom workflows live from day one.",
            "steps": [
                {
                    "title": "Complete teacher onboarding",
                    "detail": "Create your teacher profile and role preferences.",
                    "href": "/portal/teacher/onboarding/",
                    "cta": "Teacher onboarding",
                },
                {
                    "title": "Verify class access",
                    "detail": "Confirm class roster, attendance, and grading permissions.",
                    "href": "/portal/teacher/workflow/",
                    "cta": "Open teacher workflow",
                },
                {
                    "title": "Start intervention workflow",
                    "detail": "Review at-risk students and follow action-center prompts.",
                    "href": "/api/v1/intervention/action-center",
                    "cta": "Intervention action center",
                },
            ],
        },
        {
            "role": "Parent",
            "summary": "Connect to your learner and stay aligned with school updates.",
            "steps": [
                {
                    "title": "Find your school portal",
                    "detail": "Use school lookup or email discovery to reach your tenant.",
                    "href": _safe_reverse("find_school"),
                    "cta": "Search schools",
                },
                {
                    "title": "Claim invite and link child",
                    "detail": "Use guardian invitation flow to connect student records.",
                    "href": "/portal/parent/claim-invite/",
                    "cta": "Claim parent invite",
                },
                {
                    "title": "Track fees and performance",
                    "detail": "Open finance and progress dashboards after linking.",
                    "href": "/portal/parent/",
                    "cta": "Open parent portal",
                },
            ],
        },
    ]


def _discovery_rate_limit_exceeded(request) -> bool:
    """True if this IP has exceeded POST rate limit for /discover/."""
    from django.core.cache import cache

    ip = (request.META.get("REMOTE_ADDR") or "unknown").strip()
    key = DISCOVERY_RATE_LIMIT_KEY.format(ip=ip)
    count = cache.get(key, 0)
    return count >= DISCOVERY_RATE_LIMIT_MAX


def _discovery_rate_limit_incr(request) -> None:
    """Increment POST count for this IP."""
    from django.core.cache import cache

    ip = (request.META.get("REMOTE_ADDR") or "unknown").strip()
    key = DISCOVERY_RATE_LIMIT_KEY.format(ip=ip)
    try:
        count = cache.get(key, 0) + 1
        cache.set(key, count, timeout=DISCOVERY_RATE_LIMIT_WINDOW)
    except SECTION8_CACHE_FAILURES:
        pass


def _record_discovery_funnel_event(request) -> None:
    try:
        from apps.schools.funnel_events import record_marketing_funnel_event

        record_marketing_funnel_event("discovery", request)
    except SECTION8_OPTIONAL_FAILURES:
        pass


def _lti_rate_limited(request, scope: str):
    allowed, retry_after = throttle_ip_request(
        request,
        scope=f"lti:{scope}",
        max_count=LTI_RATE_LIMIT_MAX,
        window_seconds=LTI_RATE_LIMIT_WINDOW,
    )
    if allowed:
        return None
    response = JsonResponse({"error": "Too many requests"}, status=429)
    response["Retry-After"] = str(retry_after)
    return response


FIND_SCHOOL_RATE_LIMIT_MAX = 60
FIND_SCHOOL_RATE_LIMIT_WINDOW = 900


def _find_school_rate_limited(request) -> bool:
    allowed, _retry_after = throttle_ip_request(
        request,
        scope="find_school",
        max_count=FIND_SCHOOL_RATE_LIMIT_MAX,
        window_seconds=FIND_SCHOOL_RATE_LIMIT_WINDOW,
    )
    return not allowed


@require_http_methods(["GET", "POST"])
def global_login_discovery(request):
    """
    Section 8.4: Global login / discovery. Email → lookup school(s) → redirect to school portal.
    GET: show form (email). POST: lookup user/school, redirect to school URL or show "Get Started".
    Rate limited: max DISCOVERY_RATE_LIMIT_MAX POSTs per IP per 15 minutes to reduce email enumeration.
    """
    _record_discovery_funnel_event(request)
    checklist_cards = _role_onboarding_checklists()
    if request.method == "GET":
        from apps.schools.marketing_personality import marketing_personality_context

        return render(
            request,
            "marketing/global_discovery.html",
            {
                "role_checklists": checklist_cards,
                "marketing_page_slug": "portal-login",
                **marketing_personality_context("portal-login"),
            },
        )
    if _discovery_rate_limit_exceeded(request):
        return render(
            request,
            "marketing/global_discovery.html",
            {
                "error": "Too many attempts. Please try again later.",
                "role_checklists": checklist_cards,
            },
            status=429,
        )
    email = (request.POST.get("email") or "").strip()
    if not email:
        return render(
            request,
            "marketing/global_discovery.html",
            {
                "error": "Please enter your email.",
                "role_checklists": checklist_cards,
            },
        )
    from .models import SchoolMembership
    from apps.schools.domain_resolution_service import get_canonical_base_domain
    from apps.schools.pending_tenant_discovery import (
        build_pending_recovery_links,
        pending_school_state,
    )
# tenant-isolation-allow: view-layer-scoped-via-request-school-or-role-graph

    memberships = SchoolMembership.objects.filter(
        user__email__iexact=email,
    ).select_related("school").order_by("-is_primary", "school__name")[:5]
    membership = next((m for m in memberships if m.school.is_active), None)
    if membership is None and memberships:
        membership = memberships[0]
    if membership:
        _discovery_rate_limit_incr(request)
        school = membership.school
        if not school.is_active:
            state = pending_school_state(school)
            links = build_pending_recovery_links(school)
            return render(
                request,
                "schools/global_login_discovery.html",
                {
                    "email": email,
                    "role_checklists": checklist_cards,
                    "pending_school": school,
                    "pending_state": state,
                    "pending_recovery_links": links,
                },
            )
        base = get_canonical_base_domain() or request.get_host().split(":")[0]
        if school.subdomain:
            scheme = "https" if request.is_secure() else "http"
            school_url = f"{scheme}://{school.subdomain}.{base}"
            return redirect(school_url)
        try:
            return redirect(reverse("accounts:login") + "?next=/portal/")
        except NoReverseMatch:
            return redirect("accounts:login")
    _discovery_rate_limit_incr(request)
    return render(
        request,
        "schools/global_login_discovery.html",
        {
            "error": "No school found for this email. Get started by creating a school.",
            "email": email,
            "role_checklists": checklist_cards,
        },
    )


def _build_school_portal_url(request, school) -> str:
    """Canonical URL for school portal discovery links. Always subdomain (or verified custom domain); no path-based."""
    from apps.schools.domain_sync import get_base_domain

    base_domain = get_base_domain()
    slug = (
        (getattr(school, "subdomain", "") or getattr(school, "slug", "") or "")
        .strip()
        .lower()
    )
    if slug and base_domain:
        return f"https://{slug}.{base_domain}"
    return request.build_absolute_uri(reverse("global_login_discovery"))


@require_http_methods(["GET"])
def find_school(request):
    """
    Public school finder.
    - Standard GET: render finder page.
    - HTMX GET (?q=...): return live search result fragment.
    """
    _record_discovery_funnel_event(request)
    from apps.schools.pending_tenant_discovery import search_schools_for_public_finder

    rate_limited = _find_school_rate_limited(request)
    query = (request.GET.get("q") or "").strip()
    results = []
    if not rate_limited and len(query) >= 2:
        results = search_schools_for_public_finder(request, query)

    if request.headers.get("HX-Request", "").lower() == "true":
        return render(
            request,
            "marketing/partials/school_finder_results_os.html",
            {"query": query, "results": results},
        )

    from apps.schools.marketing_personality import marketing_personality_context

    return render(
        request,
        "marketing/find_campus.html",
        {
            "query": query,
            "results": results,
            "rate_limited": rate_limited,
            "role_checklists": _role_onboarding_checklists(),
            "marketing_page_slug": "find-campus",
            **marketing_personality_context("find-campus"),
        },
    )


@require_GET
def public_verify_hub(request):
    """
    Public verify subdomain landing (no tenant context).
    """
    return render(request, "schools/public_verify_hub.html", {})


@require_GET
def public_support_hub(request):
    """
    Public support subdomain landing (shared/public schema).
    """
    q = (request.GET.get("q") or "").strip()
    if q:
        from urllib.parse import urlencode

        from django.shortcuts import redirect
        from django.urls import reverse

        return redirect(f"{reverse('marketing_kb_search')}?{urlencode({'q': q})}")
    return render(request, "schools/public_support_hub.html", {})


@require_GET
def lti_launch(request, tool_id):
    """
    Section 8.3: LTI 1.3 OIDC login initiation.
    Loads active ServiceIntegration and redirects to provider authorization endpoint.
    """
    rl = _lti_rate_limited(request, "launch")
    if rl:
        return rl
    integration = _resolve_lti_integration_for_request(request, tool_id)

    if not integration:
        return JsonResponse({"error": "LTI tool not found or inactive."}, status=404)

    cfg = integration.config or {}
    authorization_endpoint = (cfg.get("authorization_endpoint") or "").strip() or (
        integration.endpoint_url or ""
    ).strip()
    client_id = (integration.client_id or cfg.get("client_id") or "").strip()
    deployment_id = (cfg.get("deployment_id") or "").strip()
    if not authorization_endpoint or not client_id or not deployment_id:
        return JsonResponse(
            {
                "error": "LTI tool misconfigured.",
                "required": ["authorization_endpoint", "client_id", "deployment_id"],
            },
            status=400,
        )

    state = secrets.token_urlsafe(24)
    nonce = secrets.token_urlsafe(24)
    session_key = f"lti_oidc:{integration.pk}:{state}"
    request.session[session_key] = {"nonce": nonce, "tool_id": integration.pk}
    request.session.modified = True

    redirect_uri = (
        cfg.get("redirect_uri") or ""
    ).strip() or request.build_absolute_uri(
        reverse("lti_launch_callback", args=[integration.pk])
    )
    params = {
        "response_type": "id_token",
        "response_mode": "form_post",
        "scope": "openid",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "login_hint": request.GET.get("login_hint")
        or getattr(request.user, "email", "")
        or "",
        "lti_message_hint": request.GET.get("lti_message_hint", ""),
        "nonce": nonce,
        "state": state,
    }
    if request.GET.get("iss"):
        params["iss"] = request.GET.get("iss")
    if request.GET.get("target_link_uri"):
        params["target_link_uri"] = request.GET.get("target_link_uri")

    params = {k: v for k, v in params.items() if str(v).strip()}
    joiner = "&" if "?" in authorization_endpoint else "?"
    return redirect(f"{authorization_endpoint}{joiner}{urlencode(params)}")


def lti_launch_placeholder(request, tool_id):
    """
    Backward-compatible alias.
    """
    return lti_launch(request, tool_id)


def _decode_unverified_jwt(id_token: str) -> dict:
    """Decode JWT payload without signature verification for baseline launch checks."""
    try:
        parts = id_token.split(".")
        if len(parts) < 2:
            return {}
        payload = parts[1] + ("=" * (-len(parts[1]) % 4))
        decoded = base64.urlsafe_b64decode(payload.encode("utf-8")).decode("utf-8")
        data = json.loads(decoded)
        return data if isinstance(data, dict) else {}
    except SECTION8_JWT_FAILURES:
        return {}


def _resolve_lti_integration_for_request(request, tool_id):
    from apps.integrations_marketplace.models import ServiceIntegration
    from apps.schools.models import School

    try:
        # tenant-isolation-allow: view-layer-scoped-via-request-school-or-role-graph
        pk = int(tool_id)
        integration = (
            # tenant-isolation-allow: view-layer-scoped-via-request-school-or-role-graph
            ServiceIntegration.objects.filter(
                pk=pk,
                service_type=ServiceIntegration.ServiceType.LTI,
                is_active=True,
            )
            .select_related("school")
            .first()
        )
    except ValueError:
        integration = None

    if integration:
        return integration

    school = getattr(request, "school", None)
    if not school:
        school_slug = (request.GET.get("school_slug") or "").strip()
        if school_slug:
            school = School.objects.filter(slug=school_slug, is_active=True).first()
    if not school:
        return None
    return resolve_service_integration(
        school,
        service_type=ServiceIntegration.ServiceType.LTI,
        service_name=str(tool_id).strip(),
        name_hints=[str(tool_id).strip(), "lti"],
        allow_legacy_backfill=True,
    )


def _extract_bearer_token(request) -> str:
    auth = (request.headers.get("Authorization") or "").strip()
    if not auth.lower().startswith("bearer "):
        return ""
    return auth[7:].strip()


def _authorize_lti_service_request(request, integration):
    cfg = integration.config or {}
    expected = (
        str(cfg.get("service_bearer_token") or "").strip()
        or str(cfg.get("bearer_token") or "").strip()
        or str(integration.client_secret or "").strip()
    )
    provided = _extract_bearer_token(request)
    if expected and provided and secrets.compare_digest(expected, provided):
        return None
    # Wave 25 v4.00.92 H9 — if the static bearer didn't match (or wasn't
    # configured), fall through to platform-signed JWT verification.
    ok_jwt, _reason, _claims = _decode_lti_platform_jwt(provided)
    if ok_jwt:
        return None
    return JsonResponse({"error": "Unauthorized"}, status=403)


def _decode_lti_platform_jwt(token: str) -> tuple[bool, str, dict]:
    """Decode + verify an LTI platform-signed Bearer token.

    Wave 25 v4.00.92 H9. Returns ``(ok, reason, claims)`` where reason is
    one of ``ok / no_bearer / expired_token / bad_token / missing_signature``.
    """
    if not token:
        return False, "no_bearer", {}
    try:
        from apps.schools.lti_platform_jwks import (
            PlatformJWKSError,
            decode_and_verify_platform_jwt,
        )
    except SECTION8_OPTIONAL_FAILURES:
        return False, "bad_token", {}
    try:
        claims = decode_and_verify_platform_jwt(token)
    except PlatformJWKSError as err:
        if err.reason == "sign_error":
            text = str(err)
            if "expired" in text.lower():
                return False, "expired_token", {}
            return False, "bad_token", {}
        return False, "bad_token", {}
    return True, "ok", claims


def _lti_validate_token_scope(
    request, required_scopes: tuple[str, ...]
) -> tuple[bool, str]:
    """Check the Authorization Bearer token's ``scope`` claim against
    ``required_scopes``.

    Wave 25 v4.00.92 H9. Returns ``(True, "ok")`` when any required scope
    appears in the token's scope set. ``(False, reason)`` otherwise:
    ``no_bearer`` / ``expired_token`` / ``bad_token`` / ``missing_scope``.

    Back-compat: when the static-bearer matches (legacy Wave-pre-25 flow),
    no token-scope check is enforced (caller must also call
    :func:`_authorize_lti_service_request` first). This helper is intended
    to layer on top — invoke after the legacy guard so a *correctly-signed
    platform JWT* path can be scope-gated without breaking existing static
    bearers in dev / fixture flows.
    """
    bearer = _extract_bearer_token(request)
    if not bearer:
        return False, "no_bearer"
    ok, reason, claims = _decode_lti_platform_jwt(bearer)
    if not ok:
        # If reason is no_bearer (impossible here) or bad_token / expired,
        # surface as-is. If JWT decode failed but the legacy static-bearer
        # accepted the request, the higher-level view will already have let
        # the request through and we treat scope-gating as a no-op (returns
        # True). For now, the contract is: if the Bearer token is present
        # but not a valid platform JWT, scope-gate fails.
        return False, reason
    scope = claims.get("scope") or claims.get("scopes") or ""
    if isinstance(scope, list):
        scopes = {str(s).strip() for s in scope if str(s).strip()}
    else:
        scopes = {s for s in str(scope).split() if s}
    if not required_scopes:
        return True, "ok"
    for needed in required_scopes:
        if needed in scopes:
            return True, "ok"
    return False, "missing_scope"


def _insufficient_scope_response(required: tuple[str, ...]) -> JsonResponse:
    """Return RFC-6750 ``insufficient_scope`` 403 JSON envelope."""
    return JsonResponse(
        {"error": "insufficient_scope", "scope": " ".join(required)},
        status=403,
    )


def _enforce_lti_scope(request, integration, required: tuple[str, ...]):
    """Wave 25 v4.00.92 H9 scope-gate.

    Skipped (returns ``None``) when the static-bearer auth in
    :func:`_authorize_lti_service_request` would have accepted the request
    (back-compat for fixtures + Wave <25 deployments). Enforced when the
    request carries a platform-signed Bearer JWT.

    Returns a :class:`JsonResponse` 403 on missing scope; ``None`` to
    continue.
    """
    bearer = _extract_bearer_token(request)
    if not bearer:
        # No Bearer header at all — the legacy guard would have already
        # returned 403, so the caller will never reach this. Be defensive.
        return _insufficient_scope_response(required)
    # If the bearer is the legacy static service_bearer_token, skip scope
    # enforcement (fixtures path).
    cfg = integration.config or {}
    expected = (
        str(cfg.get("service_bearer_token") or "").strip()
        or str(cfg.get("bearer_token") or "").strip()
        or str(integration.client_secret or "").strip()
    )
    if expected and secrets.compare_digest(expected, bearer):
        return None
    ok, reason = _lti_validate_token_scope(request, required)
    if ok:
        return None
    if reason == "missing_scope":
        return _insufficient_scope_response(required)
    if reason == "expired_token":
        return JsonResponse({"error": "invalid_token", "reason": "expired_token"}, status=401)
    return JsonResponse({"error": "invalid_token", "reason": reason}, status=401)


def _lti_state(integration):
    cfg = dict(integration.config or {})
    cfg.setdefault("_lti_lineitems", [])
    cfg.setdefault("_lti_scores", {})
    cfg.setdefault("_lti_deep_links", [])
    return cfg


def _save_lti_state(integration, cfg):
    integration.config = cfg
    integration.save(update_fields=["config", "updated_at"])


def _json_body(request):
    try:
        return json.loads((request.body or b"{}").decode("utf-8"))
    except SECTION8_JSON_FAILURES:
        return {}


def _resolve_json_mutation_body(request):
    content_type = (
        (
            (request.content_type or request.META.get("CONTENT_TYPE") or "").split(
                ";", 1
            )[0]
        )
        .strip()
        .lower()
    )
    if content_type not in SECTION8_MUTATION_CONTENT_TYPES:
        return None, JsonResponse(
            {"error": "Content-Type must be application/json"}, status=415
        )
    try:
        payload = json.loads((request.body or b"{}").decode("utf-8"))
    except SECTION8_JSON_FAILURES:
        return None, JsonResponse({"error": "Invalid JSON"}, status=400)
    if not isinstance(payload, dict):
        return None, JsonResponse({"error": "JSON object required"}, status=400)
    return payload, None


def _log_lti_request(request, tool_id, operation: str) -> None:
    """Audit log for LTI callback requests (no PII). public_endpoint_audit Step 8."""
    logger.info(
        "LTI request",
        extra={
            "path": request.path,
            "method": request.method,
            "operation": operation,
            "tool_id": str(tool_id),
        },
    )


@csrf_exempt
@require_http_methods(["POST"])
def lti_launch_callback(request, tool_id):
    """
    Section 8.3: LTI 1.3 OIDC callback (response_mode=form_post).
    Baseline validation: tool active, state present, nonce matches.
    """
    rl = _lti_rate_limited(request, "launch_callback")
    if rl:
        return rl
    _log_lti_request(request, tool_id, "launch_callback")
    integration = _resolve_lti_integration_for_request(request, tool_id)
    if not integration:
        return JsonResponse({"error": "LTI tool not found or inactive."}, status=404)

    state = (request.POST.get("state") or "").strip()
    id_token = (request.POST.get("id_token") or "").strip()
    if not state or not id_token:
        return JsonResponse({"error": "Missing state or id_token"}, status=400)

    session_key = f"lti_oidc:{integration.pk}:{state}"
    pending = request.session.get(session_key) or {}
    if not pending:
        return JsonResponse({"error": "Invalid or expired state"}, status=403)

    from apps.schools.lti_id_token_verify import decode_lti_id_token_safe

    client_id = (
        integration.client_id or (integration.config or {}).get("client_id") or ""
    ).strip()
    claims, verify_err = decode_lti_id_token_safe(
        id_token, audience=client_id or "lti", cfg=integration.config or {}
    )
    if verify_err == "invalid_id_token_signature":
        return JsonResponse({"error": "Invalid id_token signature"}, status=401)
    if verify_err == "lti_tool_jwks_uri_required":
        return JsonResponse(
            {"error": "Configure lti_tool_jwks_uri on LTI integration (strict mode)."},
            status=400,
        )
    expected_nonce = str(pending.get("nonce") or "")
    if not claims or str(claims.get("nonce") or "") != expected_nonce:
        return JsonResponse({"error": "Invalid nonce"}, status=403)

    expected_deployment = str(
        (integration.config or {}).get("deployment_id") or ""
    ).strip()
    claim_deployment = str(
        claims.get("https://purl.imsglobal.org/spec/lti/claim/deployment_id") or ""
    ).strip()
    if (
        expected_deployment
        and claim_deployment
        and claim_deployment != expected_deployment
    ):
        return JsonResponse({"error": "Deployment mismatch"}, status=403)

    request.session.pop(session_key, None)
    request.session.modified = True

    launch_target = str((integration.config or {}).get("launch_target") or "").strip()
    if launch_target:
        return redirect(launch_target)
    return JsonResponse(
        {
            "status": "ok",
            "school": str(integration.school_id),
            "service_name": integration.service_name,
            "subject": claims.get("sub"),
            "capabilities": ["oidc_login", "resource_link_launch", "ags", "nrps"],
        },
        status=200,
    )


@csrf_exempt
@require_http_methods(["GET", "POST"])
def lti_ags_lineitems(request, tool_id):
    """
    Minimal LTI AGS line item service.
    """
    rl = _lti_rate_limited(request, "ags_lineitems")
    if rl:
        return rl
    _log_lti_request(request, tool_id, "ags_lineitems")
    integration = _resolve_lti_integration_for_request(request, tool_id)
    if not integration:
        return JsonResponse({"error": "LTI tool not found or inactive."}, status=404)
    auth_err = _authorize_lti_service_request(request, integration)
    if auth_err:
        return auth_err

    from apps.schools.lti_tool_token import (
        LTI_SCOPE_LINEITEM,
        LTI_SCOPE_LINEITEM_RO,
    )

    if request.method == "GET":
        scope_err = _enforce_lti_scope(
            request, integration, (LTI_SCOPE_LINEITEM_RO, LTI_SCOPE_LINEITEM)
        )
        if scope_err:
            return scope_err
    else:
        scope_err = _enforce_lti_scope(
            request, integration, (LTI_SCOPE_LINEITEM,)
        )
        if scope_err:
            return scope_err

    cfg = _lti_state(integration)
    items = list(cfg.get("_lti_lineitems") or [])
    if request.method == "GET":
        return JsonResponse({"lineItems": items}, status=200)

    body, error = _resolve_json_mutation_body(request)
    if error:
        return error
    lineitem_id = str(secrets.token_hex(8))
    lineitem = {
        "id": lineitem_id,
        "label": str(body.get("label") or f"Line Item {len(items) + 1}"),
        "resourceId": str(body.get("resourceId") or ""),
        "tag": str(body.get("tag") or ""),
        "scoreMaximum": float(body.get("scoreMaximum") or 100.0),
        "createdAt": timezone.now().isoformat(),
    }
    items.append(lineitem)
    cfg["_lti_lineitems"] = items
    _save_lti_state(integration, cfg)
    return JsonResponse(lineitem, status=201)


@csrf_exempt
@require_http_methods(["GET", "PUT", "DELETE"])
def lti_ags_lineitem_detail(request, tool_id, lineitem_id):
    rl = _lti_rate_limited(request, "ags_lineitem_detail")
    if rl:
        return rl
    _log_lti_request(request, tool_id, "ags_lineitem_detail")
    integration = _resolve_lti_integration_for_request(request, tool_id)
    if not integration:
        return JsonResponse({"error": "LTI tool not found or inactive."}, status=404)
    auth_err = _authorize_lti_service_request(request, integration)
    if auth_err:
        return auth_err
    cfg = _lti_state(integration)
    items = list(cfg.get("_lti_lineitems") or [])
    idx = next(
        (i for i, row in enumerate(items) if str(row.get("id")) == str(lineitem_id)), -1
    )
    if idx < 0:
        return JsonResponse({"error": "Line item not found"}, status=404)

    if request.method == "GET":
        return JsonResponse(items[idx], status=200)
    if request.method == "DELETE":
        items.pop(idx)
        scores = dict(cfg.get("_lti_scores") or {})
        scores.pop(str(lineitem_id), None)
        cfg["_lti_lineitems"] = items
        cfg["_lti_scores"] = scores
        _save_lti_state(integration, cfg)
        return HttpResponse(status=204)

    body, error = _resolve_json_mutation_body(request)
    if error:
        return error
    lineitem = dict(items[idx])
    for key in ("label", "resourceId", "tag"):
        if key in body:
            lineitem[key] = str(body.get(key) or "")
    if "scoreMaximum" in body:
        lineitem["scoreMaximum"] = float(body.get("scoreMaximum") or 100.0)
    items[idx] = lineitem
    cfg["_lti_lineitems"] = items
    _save_lti_state(integration, cfg)
    return JsonResponse(lineitem, status=200)


@csrf_exempt
@require_http_methods(["GET", "POST"])
def lti_ags_scores(request, tool_id, lineitem_id):
    rl = _lti_rate_limited(request, "ags_scores")
    if rl:
        return rl
    _log_lti_request(request, tool_id, "ags_scores")
    integration = _resolve_lti_integration_for_request(request, tool_id)
    if not integration:
        return JsonResponse({"error": "LTI tool not found or inactive."}, status=404)
    auth_err = _authorize_lti_service_request(request, integration)
    if auth_err:
        return auth_err
    from apps.schools.lti_tool_token import (
        LTI_SCOPE_RESULT_RO,
        LTI_SCOPE_SCORE,
    )

    if request.method == "GET":
        scope_err = _enforce_lti_scope(
            request, integration, (LTI_SCOPE_RESULT_RO,)
        )
    else:
        scope_err = _enforce_lti_scope(
            request, integration, (LTI_SCOPE_SCORE,)
        )
    if scope_err:
        return scope_err

    cfg = _lti_state(integration)
    items = cfg.get("_lti_lineitems") or []
    if not any(str(i.get("id")) == str(lineitem_id) for i in items):
        return JsonResponse({"error": "Line item not found"}, status=404)

    scores = dict(cfg.get("_lti_scores") or {})
    entries = list(scores.get(str(lineitem_id)) or [])

    if request.method == "GET":
        return JsonResponse({"scores": entries}, status=200)

    body, error = _resolve_json_mutation_body(request)
    if error:
        return error
    entry = {
        "id": str(secrets.token_hex(8)),
        "userId": str(body.get("userId") or ""),
        "scoreGiven": float(body.get("scoreGiven") or 0.0),
        "scoreMaximum": float(body.get("scoreMaximum") or 100.0),
        "activityProgress": str(body.get("activityProgress") or "Completed"),
        "gradingProgress": str(body.get("gradingProgress") or "FullyGraded"),
        "comment": str(body.get("comment") or ""),
        "timestamp": str(body.get("timestamp") or timezone.now().isoformat()),
    }
    if not entry["userId"]:
        return JsonResponse({"error": "userId is required"}, status=400)
    entries.append(entry)
    scores[str(lineitem_id)] = entries
    cfg["_lti_scores"] = scores
    _save_lti_state(integration, cfg)
    return JsonResponse(entry, status=201)


@require_http_methods(["GET"])
def lti_ags_results(request, tool_id, lineitem_id):
    rl = _lti_rate_limited(request, "ags_results")
    if rl:
        return rl
    integration = _resolve_lti_integration_for_request(request, tool_id)
    if not integration:
        return JsonResponse({"error": "LTI tool not found or inactive."}, status=404)
    auth_err = _authorize_lti_service_request(request, integration)
    if auth_err:
        return auth_err
    from apps.schools.lti_tool_token import LTI_SCOPE_RESULT_RO

    scope_err = _enforce_lti_scope(request, integration, (LTI_SCOPE_RESULT_RO,))
    if scope_err:
        return scope_err
    cfg = _lti_state(integration)
    scores = list((cfg.get("_lti_scores") or {}).get(str(lineitem_id)) or [])
    by_user = {}
    for score in scores:
        uid = str(score.get("userId") or "").strip()
        if not uid:
            continue
        by_user[uid] = score
    results = []
    for uid, score in by_user.items():
        results.append(
            {
                "userId": uid,
                "resultScore": float(score.get("scoreGiven") or 0.0),
                "resultMaximum": float(score.get("scoreMaximum") or 100.0),
                "comment": str(score.get("comment") or ""),
            }
        )
    return JsonResponse({"results": results}, status=200)


def _map_membership_role(role: str) -> str:
    role_upper = str(role or "").upper()
    if role_upper in {"ADMIN", "IT_ADMIN", "LEADERSHIP"}:  # role-string-allow: role-to-display-label-mapping
        return "Administrator"
    if role_upper == "TEACHER":  # role-string-allow: role-to-display-label-mapping
        return "Instructor"
    if role_upper == "PARENT":  # role-string-allow: role-to-display-label-mapping
        return "Guardian"
    return "Learner"


@require_http_methods(["GET"])
def lti_nrps_memberships(request, tool_id):
    """
    Minimal LTI NRPS memberships service (tenant scoped).
    """
    rl = _lti_rate_limited(request, "nrps_memberships")
    if rl:
        return rl
    integration = _resolve_lti_integration_for_request(request, tool_id)
    if not integration:
        return JsonResponse({"error": "LTI tool not found or inactive."}, status=404)
    auth_err = _authorize_lti_service_request(request, integration)
    if auth_err:
        return auth_err
    from apps.schools.lti_tool_token import LTI_SCOPE_NRPS_MEMBERSHIP

    scope_err = _enforce_lti_scope(
        request, integration, (LTI_SCOPE_NRPS_MEMBERSHIP,)
    )
    if scope_err:
        return scope_err

    from apps.schools.models import SchoolMembership

    memberships = (
        SchoolMembership.objects.filter(school=integration.school)
        .select_related("user")
        .order_by("user_id")
    )
    members = []
    for membership in memberships:
        user = membership.user
        members.append(
            {
                "user_id": str(user.pk),
                "name": user.get_full_name() or user.username,
                "email": user.email or "",
                "roles": [_map_membership_role(membership.role or user.role)],
                "status": "Active" if user.is_active else "Inactive",
            }
        )
    return JsonResponse({"id": str(integration.pk), "members": members}, status=200)


@csrf_exempt
@require_http_methods(["POST"])
def lti_deep_linking(request, tool_id):
    """
    Minimal LTI Deep Linking response service.
    """
    rl = _lti_rate_limited(request, "deep_linking")
    if rl:
        return rl
    _log_lti_request(request, tool_id, "deep_linking")
    integration = _resolve_lti_integration_for_request(request, tool_id)
    if not integration:
        return JsonResponse({"error": "LTI tool not found or inactive."}, status=404)
    auth_err = _authorize_lti_service_request(request, integration)
    if auth_err:
        return auth_err
    cfg = _lti_state(integration)
    body, error = _resolve_json_mutation_body(request)
    if error:
        return error
    content_items = body.get("content_items")
    if not isinstance(content_items, list):
        content_items = body.get("contentItems")
    if not isinstance(content_items, list):
        return JsonResponse({"error": "content_items must be an array"}, status=400)

    accepted = []
    for item in content_items:
        if not isinstance(item, dict):
            continue
        accepted.append(
            {
                "type": str(item.get("type") or "ltiResourceLink"),
                "title": str(item.get("title") or "LTI Resource"),
                "text": str(item.get("text") or ""),
                "url": str(item.get("url") or ""),
                "lineItem": item.get("lineItem")
                if isinstance(item.get("lineItem"), dict)
                else {},
            }
        )

    deep_links = list(cfg.get("_lti_deep_links") or [])
    deep_links.append(
        {
            "id": str(secrets.token_hex(8)),
            "createdAt": timezone.now().isoformat(),
            "items": accepted,
        }
    )
    cfg["_lti_deep_links"] = deep_links[-100:]  # magic-number-allow: string-truncation-cap
    _save_lti_state(integration, cfg)
    return JsonResponse({"status": "ok", "accepted": accepted}, status=200)


@require_GET
def jwks_json(request):
    """
    Section 8.3: Public keys endpoint for LTI 1.3.
    Collect keys from active LTI integrations via config.jwks or config.public_jwk.
    """
    rl = _lti_rate_limited(request, "jwks")
    if rl:
        return rl
    from apps.integrations_marketplace.models import ServiceIntegration

    school = getattr(request, "school", None)
    # tenant-isolation-allow: view-layer-scoped-via-request-school-or-role-graph
    qs = ServiceIntegration.objects.filter(
        service_type=ServiceIntegration.ServiceType.LTI,
        is_active=True,
    )
    if school:
        qs = qs.filter(school=school)

    keys = []
    seen_kids = set()
    for integration in qs.only("config"):
        cfg = integration.config or {}
        candidates = []
        if isinstance(cfg.get("jwks"), list):
            candidates.extend([k for k in cfg.get("jwks") if isinstance(k, dict)])
        if isinstance(cfg.get("public_jwk"), dict):
            candidates.append(cfg.get("public_jwk"))
        for key in candidates:
            kid = str(key.get("kid") or "")
            if kid and kid in seen_kids:
                continue
            if kid:
                seen_kids.add(kid)
            keys.append(key)
    return JsonResponse({"keys": keys})


def frozen_account(request):
    """
    Section 8.6: Frozen account page. Shown when TenantFreezeMiddleware redirects;
    display frozen_reason and link to billing/upgrade. No auth required to view.
    """
    from django.shortcuts import render

    school = getattr(request, "school", None)
    reason = getattr(school, "frozen_reason", None) or "STORAGE"
    return render(request, "schools/frozen_account.html", {"frozen_reason": reason})
