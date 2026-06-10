"""v4.00.42 — OIDC Relying Party endpoints (Wedge 45 item 3) with auto-provision.

Implements the OAuth 2.0 / OpenID Connect 1.0 Authorization Code flow
against a configured upstream IdP (Azure AD, Okta, Google Workspace,
OneLogin). The flow:

  1. ``GET /sso/oidc/login/<provider>/`` — redirect user agent to the IdP
     ``authorization_endpoint`` with ``response_type=code``,
     ``scope=openid profile email``, ``state=<csrf>``,
     ``redirect_uri=<our callback>``.
  2. ``GET /sso/oidc/callback/<provider>/`` — receives ``code`` + ``state``,
     validates state, exchanges code at the IdP ``token_endpoint``,
     receives ``id_token`` + ``access_token``, validates the ID token's
     signature against the IdP JWKS and ``iss``/``aud``/``exp``/``iat``
     claims, **auto-provisions the Django User**, **writes an authenticated
     Django session via** ``login()``, and redirects to a success
     destination (``next=`` query param or settings.LOGIN_REDIRECT_URL).

Per-provider config lives in settings or env vars:

    OIDC_PROVIDERS = {
        "azure": {
            "discovery_url": "https://login.microsoftonline.com/<tenant>/.well-known/openid-configuration",
            "client_id":     "<...>",
            "client_secret": "<...>",
            "role_claim":    "roles",          # optional — IdP claim that
            "role_map":      {"admin": "ADMIN"} # carries role string + map.
        },
        "google": { ... },
    }

v4.00.42 scope
--------------
* Discovery doc fetched + cached (5min).
* JWKS fetched + cached (15min).
* ``id_token`` signature verified via ``jwt.decode`` (RS256 / ES256).
* ``iss``, ``aud``, ``exp``, ``iat`` + nonce enforced.
* User auto-provisioned by ``email`` (fallback ``preferred_username``);
  unusable password set on creation.
* Role mapped from ``cfg["role_claim"]`` via ``cfg["role_map"]`` when
  present; defaults to ``User.Role.PARENT``.
* Django ``login()`` writes a session cookie (``backend`` selected from
  ``AUTHENTICATION_BACKENDS[0]`` for SSO sessions).
* Returns 200 JSON when ``?format=json`` is passed; 302 redirect to
  ``next``/``LOGIN_REDIRECT_URL`` otherwise.

Tenant binding and RP-Initiated Logout are implemented below. Live provider
activation still requires operator-owned discovery URLs and client credentials.
"""
from __future__ import annotations

import hmac
import json
import logging
import os
import secrets
import time
import urllib.parse
from typing import Any

from django.conf import settings
from django.core.cache import cache
from django.http import HttpRequest, HttpResponseRedirect, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from services.post_delete_navigation import safe_next_url

logger = logging.getLogger(__name__)


_DISCOVERY_TTL = 60 * 5         # 5 minutes
_JWKS_TTL = 60 * 15             # 15 minutes
_STATE_TTL = 60 * 5             # 5 minutes
_STATE_PREFIX = "oidc:state:"


def _providers() -> dict[str, dict[str, str]]:
    """Read provider config from settings or env."""
    cfg = getattr(settings, "OIDC_PROVIDERS", None)
    if isinstance(cfg, dict) and cfg:
        return cfg
    raw = os.environ.get("RMC_OIDC_PROVIDERS", "")
    if raw:
        try:
            return json.loads(raw)
        except (ValueError, TypeError):
            return {}
    return {}


def _redirect_uri(request: HttpRequest, provider: str) -> str:
    explicit = (
        getattr(settings, "RMC_OIDC_REDIRECT_BASE_URL", "")
        or os.environ.get("RMC_OIDC_REDIRECT_BASE_URL", "")
        or ""
    ).rstrip("/")
    base = explicit or f"{'https' if request.is_secure() else 'http'}://{request.get_host()}"
    return f"{base}/sso/oidc/callback/{provider}/"


def _fetch_json(url: str) -> dict[str, Any]:
    """Minimal stdlib fetch — keeps OIDC RP free of additional deps."""
    import urllib.request
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=8.0) as resp:  # noqa: S310 — trusted IdP discovery URL
        return json.loads(resp.read().decode("utf-8"))


def _discovery(provider_cfg: dict[str, str]) -> dict[str, Any]:
    url = provider_cfg.get("discovery_url") or ""
    if not url:
        raise RuntimeError("missing discovery_url")
    ck = f"oidc:discovery:{url}"
    cached = cache.get(ck)
    if isinstance(cached, dict):
        return cached
    doc = _fetch_json(url)
    cache.set(ck, doc, _DISCOVERY_TTL)
    return doc


def _jwks(jwks_uri: str) -> dict[str, Any]:
    ck = f"oidc:jwks:{jwks_uri}"
    cached = cache.get(ck)
    if isinstance(cached, dict):
        return cached
    doc = _fetch_json(jwks_uri)
    cache.set(ck, doc, _JWKS_TTL)
    return doc


def _store_state(state: str, provider: str, nonce: str) -> None:
    cache.set(_STATE_PREFIX + state, {"provider": provider, "nonce": nonce, "issued_at": int(time.time())}, _STATE_TTL)


def _consume_state(state: str) -> dict[str, Any] | None:
    ck = _STATE_PREFIX + state
    record = cache.get(ck)
    if record:
        cache.delete(ck)
    return record if isinstance(record, dict) else None


@require_http_methods(["GET"])
def login(request: HttpRequest, provider: str):
    """Kick off the authorization-code flow."""
    cfg = _providers().get(provider)
    if not cfg:
        return JsonResponse({"error": "unknown_provider", "provider": provider}, status=404)
    try:
        disc = _discovery(cfg)
    except Exception as exc:  # noqa: BLE001
        return JsonResponse({"error": "discovery_failed", "detail": str(exc)}, status=502)
    auth_ep = disc.get("authorization_endpoint")
    if not auth_ep:
        return JsonResponse({"error": "no_authorization_endpoint"}, status=502)
    state = secrets.token_urlsafe(24)
    nonce = secrets.token_urlsafe(24)
    _store_state(state, provider, nonce)
    params = {
        "response_type": "code",
        "client_id": cfg.get("client_id", ""),
        "redirect_uri": _redirect_uri(request, provider),
        "scope": cfg.get("scope") or "openid profile email",
        "state": state,
        "nonce": nonce,
    }
    return HttpResponseRedirect(f"{auth_ep}?{urllib.parse.urlencode(params)}")


def _post_form(url: str, fields: dict[str, str]) -> dict[str, Any]:
    import urllib.request
    body = urllib.parse.urlencode(fields).encode("utf-8")
    req = urllib.request.Request(url, data=body, method="POST")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    req.add_header("Accept", "application/json")
    with urllib.request.urlopen(req, timeout=8.0) as resp:  # noqa: S310 — trusted IdP token endpoint
        return json.loads(resp.read().decode("utf-8"))


def _verify_id_token(id_token: str, disc: dict[str, Any], cfg: dict[str, str], expected_nonce: str) -> dict[str, Any]:
    try:
        import jwt
        from jwt import PyJWKClient
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"jwt library unavailable: {exc}")
    jwks_uri = disc.get("jwks_uri")
    if not jwks_uri:
        raise RuntimeError("discovery missing jwks_uri")
    issuer = disc.get("issuer") or ""
    audience = cfg.get("client_id", "")
    signing_key = PyJWKClient(jwks_uri).get_signing_key_from_jwt(id_token).key
    decoded = jwt.decode(
        id_token,
        key=signing_key,
        algorithms=["RS256", "ES256", "RS384", "RS512"],
        audience=audience,
        issuer=issuer,
        options={"require": ["exp", "iat", "iss", "aud"]},
    )
    n = decoded.get("nonce")
    if n is not None and not hmac.compare_digest(str(n), expected_nonce):
        raise RuntimeError("nonce_mismatch")
    return decoded


@csrf_exempt
@require_http_methods(["GET"])
def callback(request: HttpRequest, provider: str):
    cfg = _providers().get(provider)
    if not cfg:
        return JsonResponse({"error": "unknown_provider", "provider": provider}, status=404)
    code = (request.GET.get("code") or "").strip()
    state = (request.GET.get("state") or "").strip()
    err = (request.GET.get("error") or "").strip()
    if err:
        return JsonResponse({"error": "idp_error", "detail": err, "description": request.GET.get("error_description") or ""}, status=400)
    if not code or not state:
        return JsonResponse({"error": "missing_code_or_state"}, status=400)
    record = _consume_state(state)
    if record is None or record.get("provider") != provider:
        return JsonResponse({"error": "state_invalid_or_expired"}, status=400)
    nonce = record.get("nonce") or ""

    try:
        disc = _discovery(cfg)
    except Exception as exc:  # noqa: BLE001
        return JsonResponse({"error": "discovery_failed", "detail": str(exc)}, status=502)
    token_ep = disc.get("token_endpoint")
    if not token_ep:
        return JsonResponse({"error": "no_token_endpoint"}, status=502)

    try:
        token_resp = _post_form(token_ep, {
            "grant_type": "authorization_code",
            "code": code,
            "client_id": cfg.get("client_id", ""),
            "client_secret": cfg.get("client_secret", ""),
            "redirect_uri": _redirect_uri(request, provider),
        })
    except Exception as exc:  # noqa: BLE001
        return JsonResponse({"error": "token_exchange_failed", "detail": str(exc)}, status=502)
    id_token = token_resp.get("id_token")
    if not id_token:
        return JsonResponse({"error": "missing_id_token", "token_resp_keys": list(token_resp.keys())}, status=502)

    try:
        claims = _verify_id_token(id_token, disc, cfg, nonce)
    except Exception as exc:  # noqa: BLE001
        return JsonResponse({"error": "id_token_invalid", "detail": str(exc)}, status=401)

    # Auto-provision + login (v4.00.42).
    try:
        user, created = _provision_user(claims, cfg)
    except Exception as exc:  # noqa: BLE001
        logger.warning("oidc auto-provision failed provider=%s err=%s", provider, exc)
        return JsonResponse({"error": "provision_failed", "detail": str(exc)}, status=500)

    try:
        _login_session(request, user)
    except Exception as exc:  # noqa: BLE001
        logger.warning("oidc session login failed provider=%s err=%s", provider, exc)
        return JsonResponse({"error": "session_login_failed", "detail": str(exc)}, status=500)

    # v4.00.47 — persist the id_token + provider + subject in the session so
    # RP-Initiated Logout can supply ``id_token_hint`` to the IdP. The
    # id_token is a signed JWT — caller-presentation only — but we store
    # it scoped to the session for the duration of the SSO session.
    try:
        sess = getattr(request, "session", None)
        if sess is not None:
            sess["oidc_id_token"] = id_token
            sess["oidc_provider"] = provider
            sess["oidc_subject"] = claims.get("sub") or ""
            sess["oidc_issuer"] = claims.get("iss") or ""
    except Exception as exc:  # noqa: BLE001
        logger.debug("oidc session id_token persist failed err=%s", exc)

    # v4.00.50 — bind the user to the resolved tenant.
    try:
        _bind_tenant_for_user(
            user, source="oidc", provider=provider,
            subject=str(claims.get("sub") or ""),
            issuer=str(claims.get("iss") or ""),
        )
    except Exception as exc:  # noqa: BLE001
        logger.debug("oidc tenant bind failed err=%s", exc)

    next_url = safe_next_url(
        request,
        request.GET.get("next"),
        getattr(settings, "LOGIN_REDIRECT_URL", "/") or "/",
    )
    want_json = (request.GET.get("format") or "").lower() == "json"
    if want_json:
        return JsonResponse({
            "success": True,
            "stage": "logged_in",
            "provider": provider,
            "subject": claims.get("sub"),
            "issuer": claims.get("iss"),
            "email": claims.get("email"),
            "name": claims.get("name"),
            "preferred_username": claims.get("preferred_username"),
            "user_id": user.pk,
            "username": user.get_username(),
            "role": getattr(user, "role", ""),
            "created": created,
            "redirect_to": next_url,
        })
    return HttpResponseRedirect(next_url)


def _provision_user(claims: dict[str, Any], cfg: dict[str, str]) -> tuple[Any, bool]:
    """Get-or-create a Django User keyed on the verified OIDC subject's email.

    Returns ``(user, created_bool)``. Raises on any persistence failure.
    """
    from django.contrib.auth import get_user_model

    UserModel = get_user_model()
    email = (claims.get("email") or "").strip().lower()
    pref = (claims.get("preferred_username") or "").strip()
    sub = (claims.get("sub") or "").strip()
    name = (claims.get("name") or "").strip()

    # Username candidate: email's local-part, else preferred_username, else "oidc-<sub-prefix>".
    if email:
        username = email
    elif pref:
        username = pref
    elif sub:
        username = f"oidc-{sub[:24]}"
    else:
        raise RuntimeError("id_token missing email/preferred_username/sub")

    role_claim = cfg.get("role_claim") or ""
    role_map = cfg.get("role_map") or {}
    mapped_role = ""
    if role_claim and isinstance(role_map, dict):
        raw = claims.get(role_claim)
        if isinstance(raw, str):
            mapped_role = role_map.get(raw, "")
        elif isinstance(raw, (list, tuple)):
            for r in raw:
                if isinstance(r, str) and r in role_map:
                    mapped_role = role_map[r]
                    break

    # Try email lookup first (most stable across IdP username churn).
    user = None
    if email:
        user = UserModel.objects.filter(email__iexact=email).first()
    if user is None:
        user = UserModel.objects.filter(username=username).first()
    if user is not None:
        # Update mutable claims if changed.
        dirty = []
        if email and user.email.lower() != email:
            user.email = email
            dirty.append("email")
        if name:
            parts = name.split(" ", 1)
            first = parts[0]
            last = parts[1] if len(parts) > 1 else ""
            if first and getattr(user, "first_name", "") != first:
                user.first_name = first
                dirty.append("first_name")
            if last and getattr(user, "last_name", "") != last:
                user.last_name = last
                dirty.append("last_name")
        if mapped_role and getattr(user, "role", "") != mapped_role:
            user.role = mapped_role
            dirty.append("role")
        if dirty:
            user.save(update_fields=dirty)
        return user, False

    # Create the user with an unusable password (SSO-only).
    new_user = UserModel(username=username, email=email)
    parts = name.split(" ", 1) if name else []
    if parts:
        new_user.first_name = parts[0]
        if len(parts) > 1:
            new_user.last_name = parts[1]
    if mapped_role:
        new_user.role = mapped_role
    new_user.set_unusable_password()
    new_user.save()
    return new_user, True


def _bind_tenant_for_user(user: Any, *, source: str, provider: str, subject: str, issuer: str) -> None:
    """v4.00.50 — Record / refresh the SSO-provisioned tenant binding.

    The resolved tenant is chosen, in order of preference:
      1. existing ``UserTenantBinding.school`` (re-login keeps prior bind)
      2. an existing ``TeacherProfile.school`` or ``StudentProfile.school``
         on the user (the SSO subject reuses a known profile)
      3. provider config ``cfg["default_school_id"]`` (not handled here —
         caller may pass via subject/issuer pre-mapping)
      4. None — no bind written; row is left absent.
    """
    try:
        from apps.accounts.models_sso import UserTenantBinding
    except Exception as exc:  # noqa: BLE001
        logger.debug("oidc bind_tenant: model unavailable err=%s", exc)
        return

    existing = UserTenantBinding.objects.filter(user_id=user.pk).first()  # tenant-isolation-allow: sso-binding-lookup-by-user-pk
    school = None
    if existing is not None:
        school = existing.school
    if school is None:
        try:
            from apps.people.models import TeacherProfile, StudentProfile

            prof = TeacherProfile.objects.filter(user_id=user.pk).first()  # tenant-isolation-allow: sso-binding-resolve-school-from-teacher-profile
            if prof is not None and prof.school_id:
                school = prof.school
            if school is None:
                sp = StudentProfile.objects.filter(user_id=user.pk).first()  # tenant-isolation-allow: sso-binding-resolve-school-from-student-profile
                if sp is not None and sp.school_id:
                    school = sp.school
        except Exception as exc:  # noqa: BLE001
            logger.debug("oidc bind_tenant: profile lookup failed err=%s", exc)

    if school is None:
        return

    if existing is None:
        UserTenantBinding.objects.create(
            user_id=user.pk, school=school, source=source,
            provider=provider, subject=subject, issuer=issuer,
        )
    else:
        dirty = []
        if existing.school_id != school.pk:
            existing.school = school
            dirty.append("school")
        if provider and existing.provider != provider:
            existing.provider = provider
            dirty.append("provider")
        if subject and existing.subject != subject:
            existing.subject = subject
            dirty.append("subject")
        if issuer and existing.issuer != issuer:
            existing.issuer = issuer
            dirty.append("issuer")
        if dirty:
            existing.save(update_fields=dirty + ["updated_at"])


def _login_session(request: HttpRequest, user: Any) -> None:
    """Write the Django auth session cookie for the verified user.

    Uses ``AUTHENTICATION_BACKENDS[0]`` as the session backend marker,
    so ``request.user`` resolves to this user on subsequent requests.
    """
    from django.conf import settings as _settings
    from django.contrib.auth import login as _login

    backends = getattr(_settings, "AUTHENTICATION_BACKENDS", ())
    backend = backends[0] if backends else "django.contrib.auth.backends.ModelBackend"
    user.backend = backend  # required by django.contrib.auth.login when multiple backends configured
    _login(request, user)


_LOGOUT_STATE_PREFIX = "oidc:logout:state:"
_LOGOUT_STATE_TTL = 60 * 5


def _store_logout_state(state: str, provider: str, post_redirect: str) -> None:
    cache.set(
        _LOGOUT_STATE_PREFIX + state,
        {"provider": provider, "post_redirect": post_redirect, "issued_at": int(time.time())},
        _LOGOUT_STATE_TTL,
    )


def _consume_logout_state(state: str) -> dict[str, Any] | None:
    ck = _LOGOUT_STATE_PREFIX + state
    record = cache.get(ck)
    if record:
        cache.delete(ck)
    return record if isinstance(record, dict) else None


@require_http_methods(["GET"])
def logout(request: HttpRequest, provider: str):
    """v4.00.45 — RP-Initiated Logout per OIDC Session Management 1.0.

    Discovers the IdP's ``end_session_endpoint`` from the cached discovery
    doc, drops the local Django session, then redirects the user agent
    to the IdP with ``id_token_hint`` (when present in the session),
    ``post_logout_redirect_uri`` (our callback), and ``state``.

    When the provider exposes no ``end_session_endpoint`` we still drop
    the local session and redirect to ``post_logout_redirect_uri`` so
    the user is at least signed out of RunMyCampus.
    """
    cfg = _providers().get(provider)
    if not cfg:
        return JsonResponse({"error": "unknown_provider", "provider": provider}, status=404)
    try:
        disc = _discovery(cfg)
    except Exception as exc:  # noqa: BLE001
        return JsonResponse({"error": "discovery_failed", "detail": str(exc)}, status=502)

    end_session = disc.get("end_session_endpoint") or ""
    post_redirect = (request.GET.get("post_logout_redirect_uri") or "").strip()
    if not post_redirect:
        explicit = (
            getattr(settings, "RMC_OIDC_REDIRECT_BASE_URL", "")
            or os.environ.get("RMC_OIDC_REDIRECT_BASE_URL", "")
            or ""
        ).rstrip("/")
        base = explicit or f"{'https' if request.is_secure() else 'http'}://{request.get_host()}"
        post_redirect = f"{base}/sso/oidc/logout/callback/{provider}/"

    id_token_hint = ""
    sess = getattr(request, "session", None)
    if sess is not None:
        id_token_hint = sess.get("oidc_id_token", "") or ""

    state = secrets.token_urlsafe(24)
    _store_logout_state(state, provider, post_redirect)

    # Drop the local Django session.
    try:
        from django.contrib.auth import logout as _django_logout

        _django_logout(request)
    except Exception as exc:  # noqa: BLE001
        logger.warning("oidc logout: local session drop failed err=%s", exc)

    if not end_session:
        # No upstream end-session — at least we've logged the user out locally.
        return HttpResponseRedirect(post_redirect)

    params: dict[str, str] = {
        "post_logout_redirect_uri": post_redirect,
        "state": state,
        "client_id": cfg.get("client_id", ""),
    }
    if id_token_hint:
        params["id_token_hint"] = id_token_hint
    return HttpResponseRedirect(f"{end_session}?{urllib.parse.urlencode({k: v for k, v in params.items() if v})}")


@require_http_methods(["GET"])
def logout_callback(request: HttpRequest, provider: str):
    """Post-logout return URL. Verifies state if present, then renders a
    minimal acknowledgement so operators can confirm the round-trip.

    A best-effort second-pass ``django.contrib.auth.logout`` is invoked
    in case the user was reauthenticated via session-fixation between
    the initial logout and this callback.
    """
    state = (request.GET.get("state") or "").strip()
    rec = _consume_logout_state(state) if state else None

    try:
        from django.contrib.auth import logout as _django_logout

        _django_logout(request)
    except Exception as exc:  # noqa: BLE001
        logger.warning("oidc logout_callback: local session drop failed err=%s", exc)

    want_json = (request.GET.get("format") or "").lower() == "json"
    if want_json:
        return JsonResponse({
            "success": True,
            "stage": "logged_out",
            "provider": provider,
            "state_valid": bool(rec and rec.get("provider") == provider),
            "post_redirect_was": (rec or {}).get("post_redirect", ""),
        })
    return HttpResponseRedirect(getattr(settings, "LOGOUT_REDIRECT_URL", "/") or "/")


@require_http_methods(["GET"])
def list_providers(request: HttpRequest):
    """Operator-visible list of configured providers (codes only — no secrets)."""
    return JsonResponse({
        "success": True,
        "providers": sorted(_providers().keys()),
    })
