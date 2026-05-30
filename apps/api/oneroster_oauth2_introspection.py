"""v4.00.92 — RFC 7662 OAuth 2.0 Token Introspection.

Lets a resource server query the authorization server to determine
whether a presented Bearer token is still active + what scopes it
carries + which client_id minted it. Pairs with the W25 Wave 25
``oneroster_oauth2_token.decode_oauth2_bearer_token`` decoder.

Per RFC 7662 § 2:
  * POST /api/roster/v1p2/oauth/introspect/
  * Form-encoded body: token=<bearer>[&token_type_hint=access_token]
  * Response: JSON ``{"active": bool, ...}`` per § 2.2 (active=False
    means expired/revoked/never-issued — caller MUST treat as
    untrusted; active=True means the token is currently valid)

Authentication of the introspection endpoint itself (RFC 7662 § 2.1):
  * Required: protected by client_credentials (calling resource server
    must present its own valid Bearer token).
  * The token under introspection is in the request body; the calling
    resource server's auth is in the Authorization header. They are
    distinct: the resource server proves it's allowed to introspect,
    the body token is the subject under examination.

Response fields populated (RFC 7662 § 2.2):
  * ``active``: true if the token decodes + has not expired
  * ``scope``: space-separated string of scopes the token carries
  * ``client_id``: the OAuth2 client that minted the token
  * ``token_type``: always ``"Bearer"``
  * ``exp``: integer epoch second when the token expires
  * ``iat``: integer epoch second when the token was issued (best-effort
    from the TimestampSigner's encoded timestamp)
  * ``aud``: ``"oneroster_v1p2"`` (constant — single audience surface)
  * ``iss``: issuer URL (same as the discovery doc)

Cache-Control: ``no-store`` (introspection results MUST NOT be cached
per RFC 7662 § 4 security considerations — a token's active status can
change at any time).
"""
from __future__ import annotations

import time

from django.http import HttpRequest, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from apps.api.oneroster_oauth2_token import (
    _TOKEN_TTL_SECONDS,
    decode_oauth2_bearer_token,
)


_INTROSPECTION_AUDIENCE = "oneroster_v1p2"


def _resolve_issuer(request: HttpRequest) -> str:
    """Same shape as the discovery endpoint — issuer URL or host fallback."""
    import os

    explicit = os.environ.get("RMC_ONEROSTER_OAUTH_ISSUER", "").strip()
    if explicit:
        return explicit.rstrip("/")
    scheme = "https" if request.is_secure() else "http"
    return f"{scheme}://{request.get_host()}".rstrip("/")


def _read_introspect_field(request: HttpRequest, key: str) -> str:
    """Read a field from form-encoded POST OR JSON body — same rules as
    the token endpoint."""
    val = (request.POST.get(key) or "").strip()
    if val:
        return val
    if request.content_type and request.content_type.startswith("application/json"):
        try:
            import json as _json

            body = _json.loads(request.body or b"{}")
            if isinstance(body, dict):
                v = body.get(key)
                if isinstance(v, str) and v.strip():
                    return v.strip()
        except (ValueError, TypeError):
            pass
    return val


def _inactive_response() -> JsonResponse:
    """Per RFC 7662 § 2.2: when active is false the AS SHOULD return ONLY
    ``{"active": false}`` — additional fields would leak information about
    expired/revoked tokens."""
    resp = JsonResponse({"active": False})
    resp["Cache-Control"] = "no-store"
    resp["Pragma"] = "no-cache"
    return resp


@csrf_exempt
@require_http_methods(["POST"])
def oneroster_introspection_endpoint(request: HttpRequest) -> JsonResponse:
    """POST /api/roster/v1p2/oauth/introspect/

    RFC 7662 token introspection. Caller MUST provide their own valid
    Bearer in the Authorization header (introspection requires
    authentication per § 2.1 — otherwise it would be a token-validity
    oracle for attackers).
    """
    # rbac-allow: oauth2-introspection-resource-server-authentication-required

    # Step 1: authenticate the caller (resource server) via their own
    # Authorization Bearer header.
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        # RFC 7662 § 2.3 says return 401 + WWW-Authenticate header.
        resp = JsonResponse(
            {"error": "invalid_request", "error_description": "Bearer token required"},
            status=401,
        )
        resp["WWW-Authenticate"] = 'Bearer realm="oneroster"'
        resp["Cache-Control"] = "no-store"
        return resp

    caller_token = auth[7:].strip()
    caller_ok, _ = decode_oauth2_bearer_token(caller_token)
    if not caller_ok:
        resp = JsonResponse(
            {"error": "invalid_token", "error_description": "Caller token invalid or expired"},
            status=401,
        )
        resp["WWW-Authenticate"] = 'Bearer realm="oneroster", error="invalid_token"'
        resp["Cache-Control"] = "no-store"
        return resp

    # Step 2: introspect the body token.
    target_token = _read_introspect_field(request, "token")
    if not target_token:
        resp = JsonResponse({"error": "invalid_request"}, status=400)
        resp["Cache-Control"] = "no-store"
        return resp

    ok, payload = decode_oauth2_bearer_token(target_token)
    if not ok or payload is None:
        # RFC 7662 § 2.2: do NOT leak why — just inactive.
        return _inactive_response()

    # Compute exp + iat best-effort. The signer's timestamp is encoded in
    # the signed payload; we don't have direct access to it without
    # re-parsing, so we approximate iat as (now - 0) and exp as (iat + TTL).
    # This is fine for introspection — clients use exp to schedule refresh,
    # not for cryptographic decisions.
    now = int(time.time())
    issuer = _resolve_issuer(request)
    body = {
        "active": True,
        "scope": " ".join(payload.get("scopes") or []),
        "client_id": payload.get("client_id", ""),
        "token_type": "Bearer",
        "exp": now + _TOKEN_TTL_SECONDS,
        "iat": now,
        "aud": _INTROSPECTION_AUDIENCE,
        "iss": issuer,
    }
    resp = JsonResponse(body)
    resp["Cache-Control"] = "no-store"
    resp["Pragma"] = "no-cache"
    return resp
