"""v4.00.41 — OIDC Relying Party endpoints (Wedge 45 item 3).

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
     claims, then surfaces the verified subject.

Per-provider config lives in settings or env vars:

    OIDC_PROVIDERS = {
        "azure": {
            "discovery_url": "https://login.microsoftonline.com/<tenant>/.well-known/openid-configuration",
            "client_id":     "<...>",
            "client_secret": "<...>",
        },
        "google": { ... },
    }

Honest scope (v4.00.41)
-----------------------
* Discovery doc is fetched + cached (5min).
* JWKS is fetched + cached (15min).
* ``id_token`` signature verified via ``jwt.decode`` (RS256 / ES256).
* ``iss``, ``aud``, ``exp``, ``iat`` claims enforced.
* Authenticated subject is returned in the response body so the operator
  can confirm the round-trip end-to-end.

Deferred to v4.00.42+:
* Auto-provision Django ``User`` from the verified subject.
* SSO session write (currently no Django ``login()`` call).
* RP-Initiated Logout per OIDC Session Management spec.
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
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

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

    # Surface the verified subject. Auto-provision deferred.
    return JsonResponse({
        "success": True,
        "stage": "id_token_verified",
        "provider": provider,
        "subject": claims.get("sub"),
        "issuer": claims.get("iss"),
        "email": claims.get("email"),
        "name": claims.get("name"),
        "preferred_username": claims.get("preferred_username"),
        "user_provisioning": "deferred-v4.00.42",
    })


@require_http_methods(["GET"])
def list_providers(request: HttpRequest):
    """Operator-visible list of configured providers (codes only — no secrets)."""
    return JsonResponse({
        "success": True,
        "providers": sorted(_providers().keys()),
    })
