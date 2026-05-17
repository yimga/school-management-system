"""
Generic OAuth2 connect/complete dance, driven by the connector registry.

Every OAuth-capable connector in `connector_registry.py` advertises
authorize_url, token_url, default_scopes, scope_separator, and optional
PKCE / extra params. This module turns that metadata into the actual
HTTP flow:

  GET  /integrations/connect/<slug>/?campus=<id>
       → builds state, stores in session, redirects browser to authorize_url
  GET  /integrations/callback/<slug>/?code=...&state=...
       → validates state, exchanges code for tokens at token_url, upserts
         a `ServiceIntegration` row at the scope encoded in state.

All credentials live in `ServiceIntegration.config` (per-school or per-campus
row); the platform-level `client_id` / `client_secret` come from env via
`resolve_oauth_client_credentials()`. School admins never type a client_id —
they only consent.

State payload (HMAC-signed via Django's signing):
  {
    "slug": "<connector slug>",
    "school_id": <int>,
    "campus_id": <int|null>,
    "user_id": <int>,
    "code_verifier": "<pkce verifier>" (when connector.pkce is True),
    "redirect_back": "<url>" (optional success redirect),
    "nonce": "<urlsafe random>",
  }

The state is also stored in `request.session["oauth_state_<slug>"]` for
secondary validation — both must match before we exchange a code.
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import secrets
from typing import Any
from urllib.parse import urlencode

from django.conf import settings
from django.core.signing import BadSignature, TimestampSigner
from django.urls import reverse

from apps.integrations_marketplace.connector_registry import (
    AUTH_KIND_OAUTH2,
    Connector,
    get_connector,
    resolve_oauth_client_credentials,
)

logger = logging.getLogger(__name__)

_STATE_SIGNER_SALT = "integrations_marketplace.oauth.state"
_STATE_MAX_AGE_SECONDS = 600  # 10 minutes


# ---------------------------------------------------------------------------
# PKCE helpers (RFC 7636)
# ---------------------------------------------------------------------------

def _pkce_pair() -> tuple[str, str]:
    """Return (code_verifier, code_challenge) using S256."""
    verifier = base64.urlsafe_b64encode(secrets.token_bytes(64)).rstrip(b"=").decode()
    digest = hashlib.sha256(verifier.encode()).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
    return verifier, challenge


# ---------------------------------------------------------------------------
# State payload (signed)
# ---------------------------------------------------------------------------

def _sign_state(payload: dict[str, Any]) -> str:
    signer = TimestampSigner(salt=_STATE_SIGNER_SALT)
    return signer.sign(json.dumps(payload, separators=(",", ":"), sort_keys=True))


def _unsign_state(state: str) -> dict[str, Any] | None:
    if not state:
        return None
    signer = TimestampSigner(salt=_STATE_SIGNER_SALT)
    try:
        raw = signer.unsign(state, max_age=_STATE_MAX_AGE_SECONDS)
    except BadSignature:
        return None
    try:
        payload = json.loads(raw)
    except (TypeError, ValueError):
        return None
    if not isinstance(payload, dict):
        return None
    return payload


# ---------------------------------------------------------------------------
# Public entry points
# ---------------------------------------------------------------------------

def _effective_scopes(connector: Connector, *, school, campus) -> tuple[list[str], str]:
    """v2.79 follow-up: per-tenant scope override.

    A tenant that wants to narrow the default scopes can pre-seed the
    intended row's `config["scopes_override"]` with either a list of scope
    strings or a single space/comma-separated string. We re-validate that
    every requested scope is a subset of the connector's declared
    `default_scopes` so a tenant can NEVER *widen* scopes beyond what we
    documented at registration time — only narrow.

    Returns (effective_scopes, source) where source ∈
    {"default", "tenant_override", "tenant_override_rejected_widening"}.
    """
    default = list(connector.default_scopes)
    if school is None:
        return default, "default"
    try:
        from apps.integrations_marketplace.resolver import resolve_connector_config
        resolved = resolve_connector_config(connector.slug, school=school, campus=campus)
    except Exception:  # noqa: BLE001 — resolver hiccup shouldn't block the dance
        return default, "default"
    cfg = getattr(resolved, "config", None) or {}
    raw = cfg.get("scopes_override")
    if not raw:
        return default, "default"
    if isinstance(raw, str):
        candidates = [s.strip() for s in raw.replace(",", " ").split() if s.strip()]
    elif isinstance(raw, (list, tuple)):
        candidates = [str(s).strip() for s in raw if str(s).strip()]
    else:
        return default, "default"
    default_set = set(default)
    widening = [s for s in candidates if s not in default_set]
    if widening:
        logger.warning(
            "OAuth scope override rejected for connector=%s school=%s — "
            "requested scopes are not a subset of defaults: %s",
            connector.slug, getattr(school, "pk", None), widening,
        )
        return default, "tenant_override_rejected_widening"
    # Preserve order from the tenant config; deduplicate.
    seen: set[str] = set()
    narrowed: list[str] = []
    for s in candidates:
        if s not in seen:
            seen.add(s)
            narrowed.append(s)
    return narrowed or default, "tenant_override"


def build_authorize_redirect(
    *,
    request,
    connector_slug: str,
    school,
    campus=None,
    redirect_back: str = "",
) -> tuple[str, dict[str, Any]] | tuple[None, dict[str, Any]]:
    """
    Build the upstream authorize URL and bookkeeping state. Returns
    `(url, diagnostics)` on success or `(None, diagnostics)` on refusal.

    Refusal reasons surfaced in diagnostics["reason"]:
      - unknown_connector
      - wrong_auth_kind          (connector is not OAuth2)
      - missing_client_credentials  (env client_id/secret not set)
    """
    connector = get_connector(connector_slug)
    if connector is None:
        return None, {"reason": "unknown_connector", "connector_slug": connector_slug}
    if connector.auth_kind != AUTH_KIND_OAUTH2:
        return None, {
            "reason": "wrong_auth_kind",
            "connector_slug": connector_slug,
            "auth_kind": connector.auth_kind,
        }

    client_id, client_secret = resolve_oauth_client_credentials(connector.slug)
    if not client_id or not client_secret:
        return None, {
            "reason": "missing_client_credentials",
            "connector_slug": connector_slug,
            "env_var_hint": (
                f"INTEGRATIONS_{connector.slug.upper()}_CLIENT_ID / _CLIENT_SECRET"
            ),
        }
    # v3.4 — refuse NEW connections to deprecated connectors. We allow re-OAuth
    # of an existing row (so tenants mid-flow aren't stranded) by checking if
    # a row already exists at this scope; only first-time connects are blocked.
    if connector.deprecated:
        try:
            from apps.siteconfig.models_platform_catalog import ServiceIntegration
            existing = ServiceIntegration.objects.filter(
                school=school,
                campus=campus,
                connector_slug__iexact=connector.slug,
            ).exists()
        except Exception:  # noqa: BLE001 — defensive: DB hiccup blocks the dance correctly
            existing = False
        if not existing:
            return None, {
                "reason": "connector_deprecated",
                "connector_slug": connector_slug,
                "deprecation_note": connector.deprecation_note,
            }

    payload: dict[str, Any] = {
        "slug": connector.slug,
        "school_id": getattr(school, "pk", None),
        "campus_id": getattr(campus, "pk", None) if campus is not None else None,
        "user_id": getattr(getattr(request, "user", None), "pk", None),
        "nonce": secrets.token_urlsafe(16),
        "redirect_back": redirect_back or "",
    }

    code_challenge = ""
    if connector.pkce:
        verifier, challenge = _pkce_pair()
        payload["code_verifier"] = verifier
        code_challenge = challenge

    state = _sign_state(payload)
    request.session[f"oauth_state_{connector.slug}"] = state
    request.session.modified = True

    redirect_uri = _absolute_callback_url(request=request, connector=connector)
    scopes, scope_source = _effective_scopes(connector, school=school, campus=campus)
    params: dict[str, str] = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": connector.scope_separator.join(scopes),
        "state": state,
    }
    if code_challenge:
        params["code_challenge"] = code_challenge
        params["code_challenge_method"] = "S256"
    params.update(connector.extra_authorize_params)

    url = f"{connector.authorize_url}?{urlencode(params)}"
    return url, {
        "reason": "ok",
        "redirect_uri": redirect_uri,
        "scope": params["scope"],
        "scope_source": scope_source,
    }


def validate_callback_state(
    *, request, connector_slug: str, state: str
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    """
    Validate `state` from the OAuth callback. Returns
    `(payload, diagnostics)` on success or `(None, diagnostics)` on failure.
    """
    payload = _unsign_state(state)
    if payload is None:
        return None, {"reason": "bad_signature_or_expired"}
    if payload.get("slug") != connector_slug:
        return None, {
            "reason": "slug_mismatch",
            "payload_slug": payload.get("slug"),
            "requested_slug": connector_slug,
        }
    session_state = (request.session or {}).get(f"oauth_state_{connector_slug}", "")
    if not session_state or session_state != state:
        return None, {"reason": "session_state_mismatch"}
    return payload, {"reason": "ok"}


def build_token_exchange_payload(
    *,
    request,
    connector: Connector,
    code: str,
    state_payload: dict[str, Any],
) -> dict[str, Any]:
    """
    Build the POST body for the upstream token endpoint.

    Note: we deliberately do NOT perform the HTTP request here — callers (and
    tests) inject the transport. This keeps the module sync/async-agnostic and
    side-effect-free.
    """
    client_id, client_secret = resolve_oauth_client_credentials(connector.slug)
    body: dict[str, Any] = {
        "grant_type": "authorization_code",
        "code": code,
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": _absolute_callback_url(request=request, connector=connector),
    }
    verifier = state_payload.get("code_verifier")
    if connector.pkce and verifier:
        body["code_verifier"] = verifier
    return body


def persist_oauth_tokens(
    *,
    connector: Connector,
    school,
    campus,
    token_response: dict[str, Any],
):
    """
    Upsert a `ServiceIntegration` row at the (school, campus) scope with the
    OAuth token response. Returns the saved row.

    `token_response` is what the upstream returned from the token endpoint —
    minimum keys we look for: access_token, refresh_token, expires_in, scope.
    Extra keys are preserved in `config` for connector-specific use
    (e.g. Slack's `team`, Zoom's `account_id`).
    """
    from apps.siteconfig.models_platform_catalog import ServiceIntegration

    if not isinstance(token_response, dict):
        raise ValueError("token_response must be a dict")

    access_token = str(token_response.get("access_token") or "").strip()
    if not access_token:
        raise ValueError("token_response missing access_token")

    cfg: dict[str, Any] = dict(token_response)
    cfg.setdefault("connector_slug", connector.slug)
    scope_str = str(token_response.get("scope") or "").strip()
    if scope_str:
        scopes = [s for s in scope_str.replace(",", " ").split() if s]
    else:
        scopes = list(connector.default_scopes)

    defaults = {
        "service_type": _service_type_for(connector),
        "connector_slug": connector.slug,
        "config": cfg,
        "enabled_scopes": scopes,
        "is_active": True,
    }
    row, _created = ServiceIntegration.objects.update_or_create(
        school=school,
        campus=campus,
        service_name=connector.slug,
        defaults=defaults,
    )
    # v3.4 — fire the lifecycle signal so per-app receivers can subscribe to
    # push notifications (calendar/mail), warm caches, etc. send_robust isolates
    # subscriber crashes from the OAuth dance.
    try:
        from apps.integrations_marketplace.signals import connector_connected
        connector_connected.send_robust(
            sender="integrations_marketplace.connector",
            row=row, connector=connector.slug, school=school, campus=campus,
            action="reconnected" if not _created else "connected",
        )
    except Exception:  # noqa: BLE001 — never break the OAuth dance on signal dispatch
        logger.exception(
            "connector_connected dispatch crashed for %s", connector.slug
        )
    return row


def _service_type_for(connector: Connector) -> str:
    """Map a connector to the existing ServiceIntegration.ServiceType enum."""
    from apps.siteconfig.models_platform_catalog import ServiceIntegration

    return ServiceIntegration.ServiceType.OAUTH


def _absolute_callback_url(*, request, connector: Connector) -> str:
    """Build the absolute redirect_uri for a connector's OAuth callback."""
    try:
        relative = reverse(
            "integrations_marketplace:oauth_callback",
            kwargs={"connector_slug": connector.slug},
        )
    except Exception:  # noqa: BLE001 — reverse can raise NoReverseMatch
        relative = f"/integrations/callback/{connector.slug}/"
    base = (
        getattr(settings, "OAUTH_CALLBACK_BASE_URL", "")
        or _request_origin(request)
    )
    return f"{base.rstrip('/')}{relative}"


def _request_origin(request) -> str:
    if request is None:
        return ""
    scheme = "https" if request.is_secure() else "http"
    host = request.get_host() if hasattr(request, "get_host") else ""
    return f"{scheme}://{host}" if host else ""


__all__ = [
    "_effective_scopes",
    "build_authorize_redirect",
    "build_token_exchange_payload",
    "persist_oauth_tokens",
    "validate_callback_state",
]
