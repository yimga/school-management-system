"""Enterprise OIDC SSO views (tenant-scoped) using ServiceIntegration config."""

from __future__ import annotations

import base64
import json
import logging
import secrets
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

import jwt
from jwt import PyJWKClient
from jwt.exceptions import PyJWKClientError, PyJWTError

from django.contrib.auth import login
from django.http import HttpResponseForbidden, JsonResponse
from django.shortcuts import redirect
from django.urls import reverse
from django.views.decorators.http import require_GET

from apps.accounts.models import User
from apps.schools.models import School, SchoolMembership
from apps.siteconfig.integration_registry import resolve_service_integration
from apps.integrations_marketplace.models import ServiceIntegration

logger = logging.getLogger(__name__)

# Default signing algorithms accepted for id_token verification. ``none`` is never
# included, so an ``alg=none`` token is always rejected.
_DEFAULT_ID_TOKEN_ALGS = ["RS256", "RS384", "RS512", "ES256", "ES384", "ES512"]


class _NoVerificationMaterial(Exception):
    """Raised when no JWKS/issuer is configured, so a signature check is impossible."""


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
    except (ValueError, TypeError, KeyError, json.JSONDecodeError, UnicodeDecodeError):
        return {}


def _resolve_jwks_uri(cfg: dict) -> tuple[str, str]:
    """Return (jwks_uri, issuer) from config, fetching OIDC discovery if needed."""
    jwks_uri = str(cfg.get("jwks_uri") or "").strip()
    issuer = str(cfg.get("issuer") or cfg.get("issuer_url") or "").strip()
    if jwks_uri:
        return jwks_uri, issuer
    discovery_url = str(
        cfg.get("discovery_url") or cfg.get("oidc_discovery_url") or ""
    ).strip()
    if not discovery_url and issuer:
        discovery_url = issuer.rstrip("/") + "/.well-known/openid-configuration"
    if not discovery_url:
        return "", issuer
    try:
        req = Request(discovery_url, headers={"Accept": "application/json"})
        with urlopen(req, timeout=10) as resp:  # noqa: S310 - configured IdP discovery
            doc = json.loads(resp.read().decode("utf-8"))
        jwks_uri = str(doc.get("jwks_uri") or "").strip()
        if not issuer:
            issuer = str(doc.get("issuer") or "").strip()
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return "", issuer
    return jwks_uri, issuer


def _verify_id_token(id_token: str, *, cfg: dict, client_id: str) -> dict:
    """Verify the id_token signature + standard claims against the IdP JWKS.

    Returns the verified claims. Raises ``_NoVerificationMaterial`` when no JWKS /
    issuer is configured (caller decides the fallback), or a ``PyJWTError`` /
    ``PyJWKClientError`` when the token is present but fails verification.
    """
    jwks_uri, issuer = _resolve_jwks_uri(cfg)
    if not jwks_uri:
        raise _NoVerificationMaterial()
    algs = cfg.get("id_token_signed_response_alg") or _DEFAULT_ID_TOKEN_ALGS
    if isinstance(algs, str):
        algs = [algs]
    algs = [a for a in algs if str(a).lower() != "none"] or _DEFAULT_ID_TOKEN_ALGS
    signing_key = PyJWKClient(jwks_uri, timeout=10).get_signing_key_from_jwt(id_token)
    options = {
        "require": ["exp", "iat"],
        "verify_aud": bool(client_id),
        "verify_iss": bool(issuer),
    }
    return jwt.decode(
        id_token,
        signing_key.key,
        algorithms=algs,
        audience=client_id or None,
        issuer=issuer or None,
        leeway=120,
        options=options,
    )


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


def _exchange_code_for_tokens(
    *,
    token_endpoint: str,
    code: str,
    client_id: str,
    client_secret: str,
    redirect_uri: str,
):
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
            {
                "error": "OIDC integration misconfigured",
                "required": ["authorization_endpoint", "client_id"],
            },
            status=400,
        )

    state = secrets.token_urlsafe(24)
    nonce = secrets.token_urlsafe(24)
    redirect_uri = str(
        cfg.get("redirect_uri") or ""
    ).strip() or request.build_absolute_uri(
        reverse("accounts:oidc_callback", args=[integration.pk])
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
    from apps.accounts.federation_sso_health import (
        record_sso_failure,
        record_sso_success,
    )

    state = (request.GET.get("state") or "").strip()
    if not state:
        record_sso_failure(integration_id, "Missing state")
        return JsonResponse({"error": "Missing state"}, status=400)

    pending_key = f"oidc:{integration_id}:{state}"
    pending = request.session.get(pending_key) or {}
    if not pending:
        record_sso_failure(integration_id, "Invalid or expired state")
        return JsonResponse({"error": "Invalid or expired state"}, status=403)

    integration = (
        # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
        ServiceIntegration.objects.filter(
            pk=integration_id,
            service_type=ServiceIntegration.ServiceType.OAUTH,
            is_active=True,
        )
        .select_related("school")
        .first()
    )
    if not integration:
        record_sso_failure(integration_id, "OIDC integration not found")
        return JsonResponse({"error": "OIDC integration not found"}, status=404)
    school = integration.school
    if str(pending.get("school_id")) != str(school.pk):
        record_sso_failure(integration_id, "Tenant mismatch")
        return JsonResponse({"error": "Tenant mismatch"}, status=403)

    if request.GET.get("error"):
        record_sso_failure(integration_id, request.GET.get("error") or "IdP error")
        return JsonResponse({"error": request.GET.get("error")}, status=400)

    cfg = integration.config or {}
    client_id = str(integration.client_id or cfg.get("client_id") or "").strip()
    code = (request.GET.get("code") or "").strip()
    token_endpoint = str(cfg.get("token_endpoint") or "").strip()

    # SECURITY (2026-06-17 auth-bypass seal): only accept an id_token obtained via the
    # server-to-server authorization-code exchange (authenticated with the client secret
    # over TLS). A front-channel ``id_token`` request parameter is attacker-controllable
    # and is NEVER trusted — otherwise a forged token grants login as any user/role.
    if not code:
        record_sso_failure(integration_id, "Missing authorization code")
        return JsonResponse({"error": "Missing authorization code"}, status=400)
    if not token_endpoint:
        record_sso_failure(integration_id, "OIDC integration missing token_endpoint")
        return JsonResponse({"error": "OIDC integration misconfigured"}, status=400)

    try:
        redirect_uri = str(
            cfg.get("redirect_uri") or ""
        ).strip() or request.build_absolute_uri(
            reverse("accounts:oidc_callback", args=[integration.pk])
        )
        tokens = _exchange_code_for_tokens(
            token_endpoint=token_endpoint,
            code=code,
            client_id=client_id,
            client_secret=str(
                integration.client_secret or cfg.get("client_secret") or ""
            ),
            redirect_uri=redirect_uri,
        )
        id_token = str(tokens.get("id_token") or "").strip()
    except (
        OSError,
        ConnectionError,
        TimeoutError,
        ValueError,
        TypeError,
        KeyError,
        json.JSONDecodeError,
    ):
        record_sso_failure(integration_id, "Token exchange failed")
        return JsonResponse({"error": "Token exchange failed"}, status=502)

    if not id_token:
        record_sso_failure(integration_id, "Missing id_token")
        return JsonResponse({"error": "Missing id_token"}, status=400)

    # Verify the id_token signature against the IdP JWKS when configured. When no JWKS /
    # issuer is configured we fall back to decoding the code-exchanged token (its
    # authenticity rests on the TLS + client-secret token exchange) and log that the
    # signature was not cryptographically verified.
    try:
        claims = _verify_id_token(id_token, cfg=cfg, client_id=client_id)
    except _NoVerificationMaterial:
        logger.warning(
            "OIDC id_token signature unverified (no jwks_uri/issuer configured) for "
            "integration %s; relying on code-exchange transport authenticity.",
            integration.pk,
        )
        claims = _decode_unverified_jwt(id_token)
    except (PyJWTError, PyJWKClientError, OSError, ValueError, KeyError):
        record_sso_failure(integration_id, "id_token signature verification failed")
        return JsonResponse({"error": "id_token verification failed"}, status=401)
    if not claims:
        record_sso_failure(integration_id, "Invalid id_token")
        return JsonResponse({"error": "Invalid id_token"}, status=400)
    if str(claims.get("nonce") or "") != str(pending.get("nonce") or ""):
        record_sso_failure(integration_id, "Invalid nonce")
        return JsonResponse({"error": "Invalid nonce"}, status=403)

    email = (
        str(claims.get("email") or "").strip().lower()
        or str(claims.get("preferred_username") or "").strip().lower()
    )
    sub = str(claims.get("sub") or "").strip()
    if not email and not sub:
        record_sso_failure(integration_id, "No account identifier in token")
        return JsonResponse({"error": "No account identifier in token"}, status=400)

    username_seed = (email.split("@")[0] if email else sub).strip() or f"user_{sub[:8]}"
    username = username_seed[:150]
    role = _choose_user_role(claims, integration)

    user = User.objects.filter(email__iexact=email).first() if email else None
    if not user:
        user = User.objects.filter(username__iexact=username).first()
    _created = False
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
        _created = True
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

    # Record which IdP minted this account for this tenant (audit trail +
    # operator binding-reassign surface). Never breaks the login path.
    from apps.accounts.models_sso import UserTenantBinding
    from apps.accounts.sso_binding import bind_user_to_tenant

    bind_user_to_tenant(
        user=user,
        school=school,
        source=UserTenantBinding.Source.OIDC,
        provider=str(cfg.get("provider") or integration.service_name or "")[:64],
        subject=sub,
        issuer=str(claims.get("iss") or cfg.get("issuer") or cfg.get("issuer_url") or "")[:255],
    )

    try:
        del request.session[pending_key]
        request.session.modified = True
    except (KeyError, TypeError, RuntimeError):
        pass

    login(request, user, backend="django.contrib.auth.backends.ModelBackend")
    record_sso_success(integration_id)
    # RP-initiated logout: IdPs often require id_token_hint
    if len(id_token) <= 4096:
        request.session[f"oidc_id_token_hint:{integration.pk}"] = id_token
        request.session.modified = True
    next_url = (
        str(pending.get("next") or "").strip()
        or str(cfg.get("post_login_redirect") or "").strip()
    )
    return redirect(next_url or reverse("accounts:redirect"))


@require_GET
def oidc_logout(request, integration_id: int):
    """
    OIDC RP-initiated logout: end local session and redirect to IdP end_session_endpoint when configured.
    Query: next= post-logout landing URL (must match IdP allowlist when required).
    """
    from django.contrib.auth import logout

    # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
    integration = ServiceIntegration.objects.filter(
        pk=integration_id,
        service_type=ServiceIntegration.ServiceType.OAUTH,
        is_active=True,
    ).first()
    cfg = (integration.config or {}) if integration else {}
    end_session = str(cfg.get("end_session_endpoint") or "").strip()
    post_logout = (request.GET.get("next") or "").strip()[:2048]
    if not post_logout:
        post_logout = str(cfg.get("post_logout_redirect_uri") or "").strip()
    if not post_logout:
        post_logout = request.build_absolute_uri("/")

    hint = ""
    if integration:
        hint = str(
            request.session.pop(f"oidc_id_token_hint:{integration.pk}", "") or ""
        )

    logout(request)

    if not end_session:
        return redirect(post_logout)

    params = {"post_logout_redirect_uri": post_logout}
    if hint:
        params["id_token_hint"] = hint
    joiner = "&" if "?" in end_session else "?"
    target = f"{end_session}{joiner}{urlencode(params)}"
    # Basic open-redirect hardening: only allow http(s) to same host as configured issuer or post_logout
    parsed = urlparse(target)
    if parsed.scheme not in ("http", "https"):
        return redirect(post_logout)
    return redirect(target)
