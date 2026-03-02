"""
Section 8: Industry Interoperability — landing, Caddy ask, LTI placeholder, global login.
"""
import os
import json
import base64
import secrets
from urllib.parse import urlencode
from django.http import HttpResponse, HttpResponseForbidden, HttpResponseNotFound, JsonResponse
from django.conf import settings
from django.views.decorators.http import require_GET
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.shortcuts import redirect, render
from django.db.models import Q
from django.urls import reverse
from django.utils import timezone

from apps.api.rate_limit import throttle_ip_request
from apps.siteconfig.integration_registry import resolve_service_integration


def _caddy_ip_allowed(request) -> bool:
    """If CADDY_CHECK_ALLOWED_IPS is set (comma-separated), only those IPs are allowed. Otherwise all allowed."""
    allowed = os.getenv("CADDY_CHECK_ALLOWED_IPS", "").strip()
    if not allowed:
        return True
    remote = (request.META.get("REMOTE_ADDR") or "").strip()
    return remote in [ip.strip() for ip in allowed.split(",") if ip.strip()]


CADDY_CHECK_RATE_LIMIT_WINDOW = 60 * 15
CADDY_CHECK_RATE_LIMIT_MAX = 180


@require_GET
@csrf_exempt
def verify_caddy_domain(request):
    """
    Section 8.5: Caddy on-demand TLS "ask" endpoint.
    GET ?domain=greenwood.yoursystem.com → 200 if domain allowed, 404 otherwise.
    If CADDY_CHECK_ALLOWED_IPS is set (comma-separated), only those IPs get 200/404; others get 403.
    """
    if not _caddy_ip_allowed(request):
        return HttpResponseForbidden("IP not allowed")
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
    except Exception:
        cache = None

    # 1. Runtime domain table (django-tenants): authoritative routing map.
    try:
        from apps.customers.models import Domain
        if Domain.objects.filter(domain=domain_lower, tenant__school__is_active=True).exists():
            if cache:
                try:
                    cache.set(cache_key, True, timeout=cache_ttl)
                except Exception:
                    pass
            return HttpResponse(status=200)
    except Exception:
        pass

    # 2. SchoolDomain (shared schema): multiple domains per tenant, is_verified
    try:
        from .models import SchoolDomain
        if SchoolDomain.objects.filter(domain=domain_lower, is_verified=True, school__is_active=True).exists():
            if cache:
                try:
                    cache.set(cache_key, True, timeout=cache_ttl)
                except Exception:
                    pass
            return HttpResponse(status=200)
    except Exception:
        pass

    # 3. Legacy: School.subdomain and School.custom_domain
    from .models import School
    subdomain = domain_lower.split(".")[0] if "." in domain_lower else domain_lower
    if School.objects.filter(subdomain=subdomain, is_active=True).exists():
        if cache:
            try:
                cache.set(cache_key, True, timeout=cache_ttl)
            except Exception:
                pass
        return HttpResponse(status=200)
    if School.objects.filter(custom_domain=domain_lower, custom_domain_verified=True, is_active=True).exists():
        if cache:
            try:
                cache.set(cache_key, True, timeout=cache_ttl)
            except Exception:
                pass
        return HttpResponse(status=200)

    if cache:
        try:
            cache.set(cache_key, False, timeout=cache_ttl)
        except Exception:
            pass
    return HttpResponseNotFound("Domain not recognized")


DISCOVERY_RATE_LIMIT_KEY = "discovery_post:{ip}"
DISCOVERY_RATE_LIMIT_MAX = 10
DISCOVERY_RATE_LIMIT_WINDOW = 60 * 15  # 15 minutes
LTI_RATE_LIMIT_WINDOW = 60 * 15
LTI_RATE_LIMIT_MAX = 240


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
    except Exception:
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


@require_http_methods(["GET", "POST"])
def global_login_discovery(request):
    """
    Section 8.4: Global login / discovery. Email → lookup school(s) → redirect to school portal.
    GET: show form (email). POST: lookup user/school, redirect to school URL or show "Get Started".
    Rate limited: max DISCOVERY_RATE_LIMIT_MAX POSTs per IP per 15 minutes to reduce email enumeration.
    """
    if request.method == "GET":
        return render(request, "schools/global_login_discovery.html", {})
    if _discovery_rate_limit_exceeded(request):
        return render(request, "schools/global_login_discovery.html", {
            "error": "Too many attempts. Please try again later.",
        }, status=429)
    email = (request.POST.get("email") or "").strip()
    if not email:
        return render(request, "schools/global_login_discovery.html", {"error": "Please enter your email."})
    from .models import SchoolMembership
    from apps.schools.host_routing import get_canonical_base_domain
    memberships = SchoolMembership.objects.filter(
        user__email__iexact=email,
        school__is_active=True,
    ).select_related("school")[:1]
    membership = memberships.first()
    if membership:
        _discovery_rate_limit_incr(request)
        school = membership.school
        base = get_canonical_base_domain() or request.get_host().split(":")[0]
        if school.subdomain:
            scheme = "https" if request.is_secure() else "http"
            school_url = f"{scheme}://{school.subdomain}.{base}"
            return redirect(school_url)
        try:
            from django.urls import reverse
            return redirect(reverse("accounts:login") + f"?next=/portal/")
        except Exception:
            return redirect("accounts:login")
    _discovery_rate_limit_incr(request)
    return render(request, "schools/global_login_discovery.html", {
        "error": "No school found for this email. Get started by creating a school.",
        "email": email,
    })


def _build_school_portal_url(request, school) -> str:
    """Canonical URL for school portal discovery links."""
    from apps.schools.domain_sync import get_base_domain

    base_domain = get_base_domain()
    subdomain = (getattr(school, "subdomain", "") or getattr(school, "slug", "") or "").strip().lower()
    if subdomain and base_domain:
        return f"https://{subdomain}.{base_domain}"

    # If no canonical subdomain is available, send user back to global discovery.
    return request.build_absolute_uri(reverse("global_login_discovery"))


@require_http_methods(["GET"])
def find_school(request):
    """
    Public school finder.
    - Standard GET: render finder page.
    - HTMX GET (?q=...): return live search result fragment.
    """
    from apps.schools.models import School

    query = (request.GET.get("q") or "").strip()
    results = []
    if len(query) >= 2:
        schools = (
            School.objects.filter(is_active=True)
            .filter(Q(name__icontains=query) | Q(slug__icontains=query) | Q(subdomain__icontains=query))
            .order_by("name")[:8]
        )
        for school in schools:
            results.append(
                {
                    "name": school.name,
                    "slug": school.slug,
                    "portal_url": _build_school_portal_url(request, school),
                }
            )

    if request.headers.get("HX-Request", "").lower() == "true":
        return render(
            request,
            "schools/partials/school_finder_results.html",
            {"query": query, "results": results},
        )

    return render(
        request,
        "schools/find_school.html",
        {"query": query, "results": results},
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
    authorization_endpoint = (
        (cfg.get("authorization_endpoint") or "").strip()
        or (integration.endpoint_url or "").strip()
    )
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
        (cfg.get("redirect_uri") or "").strip()
        or request.build_absolute_uri(reverse("lti_launch_callback", args=[integration.pk]))
    )
    params = {
        "response_type": "id_token",
        "response_mode": "form_post",
        "scope": "openid",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "login_hint": request.GET.get("login_hint") or getattr(request.user, "email", "") or "",
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
    except Exception:
        return {}


def _resolve_lti_integration_for_request(request, tool_id):
    from apps.siteconfig.models import ServiceIntegration
    from apps.schools.models import School

    try:
        pk = int(tool_id)
        integration = ServiceIntegration.objects.filter(
            pk=pk,
            service_type=ServiceIntegration.ServiceType.LTI,
            is_active=True,
        ).select_related("school").first()
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
    return JsonResponse({"error": "Unauthorized"}, status=403)


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
    except Exception:
        return {}


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

    claims = _decode_unverified_jwt(id_token)
    expected_nonce = str(pending.get("nonce") or "")
    if not claims or str(claims.get("nonce") or "") != expected_nonce:
        return JsonResponse({"error": "Invalid nonce"}, status=403)

    expected_deployment = str((integration.config or {}).get("deployment_id") or "").strip()
    claim_deployment = str(
        claims.get("https://purl.imsglobal.org/spec/lti/claim/deployment_id") or ""
    ).strip()
    if expected_deployment and claim_deployment and claim_deployment != expected_deployment:
        return JsonResponse({"error": "Deployment mismatch"}, status=403)

    try:
        del request.session[session_key]
        request.session.modified = True
    except Exception:
        pass

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
    integration = _resolve_lti_integration_for_request(request, tool_id)
    if not integration:
        return JsonResponse({"error": "LTI tool not found or inactive."}, status=404)
    auth_err = _authorize_lti_service_request(request, integration)
    if auth_err:
        return auth_err

    cfg = _lti_state(integration)
    items = list(cfg.get("_lti_lineitems") or [])
    if request.method == "GET":
        return JsonResponse({"lineItems": items}, status=200)

    body = _json_body(request)
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
    integration = _resolve_lti_integration_for_request(request, tool_id)
    if not integration:
        return JsonResponse({"error": "LTI tool not found or inactive."}, status=404)
    auth_err = _authorize_lti_service_request(request, integration)
    if auth_err:
        return auth_err
    cfg = _lti_state(integration)
    items = list(cfg.get("_lti_lineitems") or [])
    idx = next((i for i, row in enumerate(items) if str(row.get("id")) == str(lineitem_id)), -1)
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

    body = _json_body(request)
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
    integration = _resolve_lti_integration_for_request(request, tool_id)
    if not integration:
        return JsonResponse({"error": "LTI tool not found or inactive."}, status=404)
    auth_err = _authorize_lti_service_request(request, integration)
    if auth_err:
        return auth_err
    cfg = _lti_state(integration)
    items = cfg.get("_lti_lineitems") or []
    if not any(str(i.get("id")) == str(lineitem_id) for i in items):
        return JsonResponse({"error": "Line item not found"}, status=404)

    scores = dict(cfg.get("_lti_scores") or {})
    entries = list(scores.get(str(lineitem_id)) or [])

    if request.method == "GET":
        return JsonResponse({"scores": entries}, status=200)

    body = _json_body(request)
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


@csrf_exempt
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
    if role_upper in {"ADMIN", "IT_ADMIN", "LEADERSHIP"}:
        return "Administrator"
    if role_upper == "TEACHER":
        return "Instructor"
    if role_upper == "PARENT":
        return "Guardian"
    return "Learner"


@csrf_exempt
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
    integration = _resolve_lti_integration_for_request(request, tool_id)
    if not integration:
        return JsonResponse({"error": "LTI tool not found or inactive."}, status=404)
    auth_err = _authorize_lti_service_request(request, integration)
    if auth_err:
        return auth_err
    cfg = _lti_state(integration)
    body = _json_body(request)
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
                "lineItem": item.get("lineItem") if isinstance(item.get("lineItem"), dict) else {},
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
    cfg["_lti_deep_links"] = deep_links[-100:]
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
    from apps.siteconfig.models import ServiceIntegration

    school = getattr(request, "school", None)
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
