"""Enterprise OIDC SSO views (tenant-scoped) using ServiceIntegration config."""

from __future__ import annotations

import base64
import json
import secrets
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from django.contrib.auth import login
from django.http import HttpResponseForbidden, JsonResponse
from django.shortcuts import redirect
from django.urls import reverse
from django.views.decorators.http import require_GET

from apps.accounts.models import User
from apps.schools.models import School, SchoolMembership
from apps.siteconfig.integration_registry import resolve_service_integration
from apps.integrations_marketplace.models import ServiceIntegration


def _resolve_school(request):
    school = getattr(request, "school", None)
    if school:
        return school
    slug = (request.GET.get("school_slug") or "").strip()
    if not slug:
        return None
    return School.objects.filter(slug=slug, is_active=True).first()


def _resolve_oidc_integration(school, integration_ref: str):
    qs = ServiceIntegration.objects.filter(
        school=school,
        service_type=ServiceIntegration.ServiceType.OAUTH,
        is_active=True,
    )
    try:
        pk = int(integration_ref)
        item = qs.filter(pk=pk).first()
        if item:
            return item
    except ValueError:
        pass
    ref = str(integration_ref).strip()
    item = qs.filter(service_name__iexact=ref).first()
    if item:
        return item
    return resolve_service_integration(
        school,
        service_type=ServiceIntegration.ServiceType.OAUTH,
        service_name=ref,
        name_hints=[ref, "oidc", "openid"],
        allow_legacy_backfill=True,
    )


def _decode_unverified_jwt(id_token: str) -> dict:
    try:
        parts = id_token.split(".")
        if len(parts) < 2:
            return {}
        payload = parts[1] + ("=" * (-len(parts[1]) % 4))
        decoded = base64.urlsafe_b64decode(payload.encode("utf-8")).decode("utf-8")
        body = json.loads(decoded)
        return body if isinstance(body, dict) else {}
    except Exception:
        return {}


def _choose_user_role(claims: dict, integration: ServiceIntegration) -> str:
    cfg = integration.config or {}
    valid_roles = {choice[0] for choice in User.Role.choices}
    default_role = str(cfg.get("default_role") or User.Role.PARENT).strip().upper()
    if default_role not in valid_roles:
        default_role = User.Role.PARENT

    role_map = cfg.get("role_map") or {}
    if not isinstance(role_map, dict):
        return default_role
    groups = claims.get("groups") or claims.get("roles") or []
    if not isinstance(groups, list):
        groups = [groups]
    for group in groups:
        mapped = str(role_map.get(str(group), "")).strip().upper()
        if mapped in valid_roles:
            return mapped
    return default_role


def _exchange_code_for_tokens(*, token_endpoint: str, code: str, client_id: str, client_secret: str, redirect_uri: str):
    form = urlencode(
        {
            "grant_type": "authorization_code",
            "code": code,
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": redirect_uri,
        }
    ).encode("utf-8")
    req = Request(
        token_endpoint,
        data=form,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    with urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode("utf-8"))


@require_GET
def oidc_start(request, integration_ref: str):
    school = _resolve_school(request)
    if not school:
        return HttpResponseForbidden("School context required.")
    integration = _resolve_oidc_integration(school, integration_ref)
    if not integration:
        return JsonResponse({"error": "OIDC integration not found"}, status=404)

    cfg = integration.config or {}
    authorization_endpoint = (
        str(cfg.get("authorization_endpoint") or "").strip()
        or (integration.endpoint_url or "").strip()
    )
    client_id = str(integration.client_id or cfg.get("client_id") or "").strip()
    if not authorization_endpoint or not client_id:
        return JsonResponse(
            {"error": "OIDC integration misconfigured", "required": ["authorization_endpoint", "client_id"]},
            status=400,
        )

    state = secrets.token_urlsafe(24)
    nonce = secrets.token_urlsafe(24)
    redirect_uri = (
        str(cfg.get("redirect_uri") or "").strip()
        or request.build_absolute_uri(reverse("accounts:oidc_callback", args=[integration.pk]))
    )
    request.session[f"oidc:{integration.pk}:{state}"] = {
        "nonce": nonce,
        "school_id": str(school.pk),
        "next": request.GET.get("next") or "",
    }
    request.session.modified = True

    scope = str(cfg.get("scope") or "openid email profile").strip()
    params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "scope": scope,
        "state": state,
        "nonce": nonce,
    }
    if request.GET.get("login_hint"):
        params["login_hint"] = request.GET.get("login_hint")
    joiner = "&" if "?" in authorization_endpoint else "?"
    return redirect(f"{authorization_endpoint}{joiner}{urlencode(params)}")


@require_GET
def oidc_callback(request, integration_id: int):
    state = (request.GET.get("state") or "").strip()
    if not state:
        return JsonResponse({"error": "Missing state"}, status=400)

    pending_key = f"oidc:{integration_id}:{state}"
    pending = request.session.get(pending_key) or {}
    if not pending:
        return JsonResponse({"error": "Invalid or expired state"}, status=403)

    integration = ServiceIntegration.objects.filter(
        pk=integration_id,
        service_type=ServiceIntegration.ServiceType.OAUTH,
        is_active=True,
    ).select_related("school").first()
    if not integration:
        return JsonResponse({"error": "OIDC integration not found"}, status=404)
    school = integration.school
    if str(pending.get("school_id")) != str(school.pk):
        return JsonResponse({"error": "Tenant mismatch"}, status=403)

    if request.GET.get("error"):
        return JsonResponse({"error": request.GET.get("error")}, status=400)

    cfg = integration.config or {}
    code = (request.GET.get("code") or "").strip()
    id_token = (request.GET.get("id_token") or "").strip()
    if not id_token and code and str(cfg.get("token_endpoint") or "").strip():
        try:
            redirect_uri = (
                str(cfg.get("redirect_uri") or "").strip()
                or request.build_absolute_uri(reverse("accounts:oidc_callback", args=[integration.pk]))
            )
            tokens = _exchange_code_for_tokens(
                token_endpoint=str(cfg.get("token_endpoint")),
                code=code,
                client_id=str(integration.client_id or cfg.get("client_id") or ""),
                client_secret=str(integration.client_secret or cfg.get("client_secret") or ""),
                redirect_uri=redirect_uri,
            )
            id_token = str(tokens.get("id_token") or "").strip()
        except Exception:
            return JsonResponse({"error": "Token exchange failed"}, status=502)

    if not id_token:
        return JsonResponse({"error": "Missing id_token"}, status=400)

    claims = _decode_unverified_jwt(id_token)
    if not claims:
        return JsonResponse({"error": "Invalid id_token"}, status=400)
    if str(claims.get("nonce") or "") != str(pending.get("nonce") or ""):
        return JsonResponse({"error": "Invalid nonce"}, status=403)

    email = (
        str(claims.get("email") or "").strip().lower()
        or str(claims.get("preferred_username") or "").strip().lower()
    )
    sub = str(claims.get("sub") or "").strip()
    if not email and not sub:
        return JsonResponse({"error": "No account identifier in token"}, status=400)

    username_seed = (email.split("@")[0] if email else sub).strip() or f"user_{sub[:8]}"
    username = username_seed[:150]
    role = _choose_user_role(claims, integration)

    user = User.objects.filter(email__iexact=email).first() if email else None
    if not user:
        user = User.objects.filter(username__iexact=username).first()
    created = False
    if not user:
        user = User.objects.create_user(
            username=username,
            email=email,
            first_name=str(claims.get("given_name") or "").strip(),
            last_name=str(claims.get("family_name") or "").strip(),
            role=role,
            password=secrets.token_urlsafe(24),
        )
        user.set_unusable_password()
        user.save(update_fields=["password"])
        created = True
    else:
        updated = False
        if email and user.email != email:
            user.email = email
            updated = True
        if not user.first_name and claims.get("given_name"):
            user.first_name = str(claims.get("given_name") or "").strip()
            updated = True
        if not user.last_name and claims.get("family_name"):
            user.last_name = str(claims.get("family_name") or "").strip()
            updated = True
        if user.role != role:
            user.role = role
            updated = True
        if updated:
            user.save()

    SchoolMembership.objects.get_or_create(
        school=school,
        user=user,
        defaults={"role": role, "is_primary": True},
    )

    try:
        del request.session[pending_key]
        request.session.modified = True
    except Exception:
        pass

    login(request, user, backend="django.contrib.auth.backends.ModelBackend")
    next_url = str(pending.get("next") or "").strip() or str(cfg.get("post_login_redirect") or "").strip()
    return redirect(next_url or reverse("accounts:redirect"))
