"""LTI 1.3 Tool Token endpoint (Wave 25 v4.00.92, H8).

Implements the platform-side **OAuth 2.0 client_credentials** grant that
LTI 1.3 tools use to mint access tokens for AGS / NRPS / Deep Linking
service calls.

Wire:
- ``POST /lti/auth/token/`` (see ``lti_tool_token_endpoint`` below).
- Tool sends ``grant_type=client_credentials`` + ``client_assertion_type=
  urn:ietf:params:oauth:client-assertion-type:jwt-bearer`` + ``client_
  assertion=<jwt>`` + ``scope=<space-separated>``.
- Helper :func:`issue_lti_tool_access_token` validates the assertion against
  the tool's ``ServiceIntegration`` row (where ``service_type=LTI``) and
  returns a Bearer token with granted scopes = requested ∩ permitted.

Standard LTI 1.3 scope URIs (IMS-defined, treated as opaque strings):

- ``https://purl.imsglobal.org/spec/lti-ags/scope/lineitem``
- ``https://purl.imsglobal.org/spec/lti-ags/scope/lineitem.readonly``
- ``https://purl.imsglobal.org/spec/lti-ags/scope/result.readonly``
- ``https://purl.imsglobal.org/spec/lti-ags/scope/score``
- ``https://purl.imsglobal.org/spec/lti-nrps/v2/scope/contextmembership.readonly``

Error responses follow RFC-6749 § 5.2 (``invalid_request`` /
``invalid_client`` / ``invalid_grant`` / ``invalid_scope`` /
``unsupported_grant_type`` / ``server_error``).

NEVER logs raw client_secret / tool assertion private bits / Bearer token.
"""

from __future__ import annotations

import importlib
import json
import logging
import secrets
import time
from typing import Any

from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from apps.schools.lti_platform_jwks import sign_platform_jwt

logger = logging.getLogger(__name__)


# --- Canonical LTI 1.3 scope URIs --------------------------------------------
LTI_SCOPE_LINEITEM = "https://purl.imsglobal.org/spec/lti-ags/scope/lineitem"
LTI_SCOPE_LINEITEM_RO = (
    "https://purl.imsglobal.org/spec/lti-ags/scope/lineitem.readonly"
)
LTI_SCOPE_RESULT_RO = (
    "https://purl.imsglobal.org/spec/lti-ags/scope/result.readonly"
)
LTI_SCOPE_SCORE = "https://purl.imsglobal.org/spec/lti-ags/scope/score"
LTI_SCOPE_NRPS_MEMBERSHIP = (
    "https://purl.imsglobal.org/spec/lti-nrps/v2/scope/contextmembership.readonly"
)
STANDARD_LTI_SCOPES: tuple[str, ...] = (
    LTI_SCOPE_LINEITEM,
    LTI_SCOPE_LINEITEM_RO,
    LTI_SCOPE_RESULT_RO,
    LTI_SCOPE_SCORE,
    LTI_SCOPE_NRPS_MEMBERSHIP,
)

JWT_BEARER_ASSERTION_TYPE = (
    "urn:ietf:params:oauth:client-assertion-type:jwt-bearer"
)
GRANT_CLIENT_CREDENTIALS = "client_credentials"

DEFAULT_TOKEN_TTL_SECONDS = 3600  # magic-number-allow: ttl-seconds


# --- Helpers -----------------------------------------------------------------


def _normalize_scope_list(value: Any) -> list[str]:
    """Convert raw scope input (str | list | None) into a deduped scope list."""
    if not value:
        return []
    if isinstance(value, str):
        candidates = value.split()
    elif isinstance(value, (list, tuple)):
        candidates = [str(v).strip() for v in value if str(v).strip()]
    else:
        return []
    seen: set[str] = set()
    out: list[str] = []
    for c in candidates:
        c = c.strip()
        if not c or c in seen:
            continue
        seen.add(c)
        out.append(c)
    return out


def _intersect_scopes(
    requested: list[str], permitted: list[str]
) -> list[str]:
    """Return ``requested ∩ permitted`` preserving requested order."""
    perm_set = set(permitted or [])
    return [s for s in requested if s in perm_set]


def _resolve_lti_integration_by_client_id(client_id: str):
    """Look up an active LTI ``ServiceIntegration`` by client_id.

    Searches BOTH the dedicated ``client_id`` column AND ``config.client_id``
    (some operator workflows save it under the JSON config blob only).
    """
    from apps.integrations_marketplace.models import ServiceIntegration

    client_id = (client_id or "").strip()
    if not client_id:
        return None
    # tenant-isolation-allow: lti-tool-token-cross-tenant-client-id-lookup
    integration = (
        ServiceIntegration.objects.filter(
            service_type=ServiceIntegration.ServiceType.LTI,
            is_active=True,
            client_id=client_id,
        )
        .select_related("school")
        .first()
    )
    if integration:
        return integration
    # Fallback: config.client_id JSON path. SQLite-friendly Python-side scan.
    # tenant-isolation-allow: lti-tool-token-cross-tenant-config-client-id-fallback
    candidates = ServiceIntegration.objects.filter(
        service_type=ServiceIntegration.ServiceType.LTI,
        is_active=True,
    ).only("config", "school_id", "client_id", "service_name", "id")
    for row in candidates.iterator():
        cfg = row.config or {}
        if str(cfg.get("client_id") or "").strip() == client_id:
            return row
        if str(cfg.get("tool_client_id") or "").strip() == client_id:
            return row
    return None


def _decode_jwt_segments(jwt: str) -> tuple[dict[str, Any], dict[str, Any], bytes, bytes]:
    """Return (header, payload, signing_input, signature) without verifying."""
    import base64

    parts = (jwt or "").split(".")
    if len(parts) != 3:
        raise ValueError("malformed_jwt")

    def _pad(s: str) -> bytes:
        return (s + "=" * (-len(s) % 4)).encode("ascii")

    try:
        header = json.loads(base64.urlsafe_b64decode(_pad(parts[0])).decode("utf-8"))
        payload = json.loads(base64.urlsafe_b64decode(_pad(parts[1])).decode("utf-8"))
        signature = base64.urlsafe_b64decode(_pad(parts[2]))
    except (ValueError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ValueError("malformed_jwt") from exc
    signing_input = f"{parts[0]}.{parts[1]}".encode("ascii")
    if not isinstance(header, dict) or not isinstance(payload, dict):
        raise ValueError("malformed_jwt")
    return header, payload, signing_input, signature


def _verify_tool_jwt_assertion(
    *, jwt_assertion: str, cfg: dict[str, Any], expected_audience: str | None = None
) -> tuple[bool, str, dict[str, Any]]:
    """Verify the tool's client_assertion JWT.

    Verification order:

    1. If ``cfg["lti_tool_jwks_url"]`` is set AND the ``jwt`` lib is installed,
       fetch JWKS and verify RS256/ES256.
    2. Else if ``cfg["lti_tool_shared_secret"]`` is set, verify HS256.
    3. Else if neither is set, accept UNVERIFIED (dev mode) but warn-log.

    Returns ``(ok, reason, claims)``. Reason ∈ {ok, malformed_jwt,
    bad_signature, expired_assertion, jwt_lib_missing, jwks_fetch_failed,
    audience_mismatch, no_verification_material}.
    """
    if not jwt_assertion:
        return False, "malformed_jwt", {}
    try:
        header, payload, signing_input, signature = _decode_jwt_segments(jwt_assertion)
    except ValueError:
        return False, "malformed_jwt", {}

    exp = int(payload.get("exp", 0) or 0)
    if exp and int(time.time()) > exp:
        return False, "expired_assertion", payload

    if expected_audience:
        aud = payload.get("aud")
        aud_list = aud if isinstance(aud, list) else [aud] if aud else []
        if expected_audience not in [str(a) for a in aud_list]:
            return False, "audience_mismatch", payload

    jwks_url = str(cfg.get("lti_tool_jwks_url") or cfg.get("tool_jwks_url") or "").strip()
    shared_secret = str(cfg.get("lti_tool_shared_secret") or "").strip()

    if jwks_url:
        try:
            jwt_mod = importlib.import_module("jwt")
            pyjwk_mod = importlib.import_module("jwt").PyJWKClient  # type: ignore[attr-defined]
        except (ImportError, AttributeError):
            return False, "jwt_lib_missing", payload
        try:
            client = pyjwk_mod(jwks_url, cache_keys=True)
            signing_key = client.get_signing_key_from_jwt(jwt_assertion)
            claims = jwt_mod.decode(
                jwt_assertion,
                signing_key.key,
                algorithms=["RS256", "ES256", "RS384", "ES384"],
                audience=expected_audience if expected_audience else None,
                options={"verify_aud": bool(expected_audience)},
            )
            return True, "ok", claims if isinstance(claims, dict) else payload
        except Exception:  # PyJWT raises a variety of errors
            logger.warning("LTI tool assertion verify failed (jwks_url present)")
            return False, "bad_signature", payload

    if shared_secret:
        try:
            jwt_mod = importlib.import_module("jwt")
            claims = jwt_mod.decode(
                jwt_assertion,
                shared_secret,
                algorithms=["HS256"],
                audience=expected_audience if expected_audience else None,
                options={"verify_aud": bool(expected_audience)},
            )
            return True, "ok", claims if isinstance(claims, dict) else payload
        except ImportError:
            return False, "jwt_lib_missing", payload
        except Exception:
            return False, "bad_signature", payload

    # Dev fallback — neither JWKS URL nor shared secret configured.
    logger.warning(
        "LTI tool assertion accepted unverified (no jwks_url + no shared_secret)"
    )
    return True, "ok", payload


def issue_lti_tool_access_token(
    *,
    client_id: str,
    requested_scopes: list[str] | str | None,
    jwt_assertion: str,
    expected_audience: str | None = None,
    ttl_seconds: int = DEFAULT_TOKEN_TTL_SECONDS,
) -> dict[str, Any]:
    """Issue a Bearer access token to an LTI tool.

    On success returns:
    ``{"ok": True, "access_token": <jws>, "token_type": "Bearer",
       "expires_in": <int>, "scope": "<space-separated granted scopes>",
       "client_id": str, "integration_id": int}``

    On failure returns an RFC-6749 § 5.2 error response:
    ``{"ok": False, "error": "...", "error_description": "...", "status": int}``.
    """
    requested = _normalize_scope_list(requested_scopes)
    integration = _resolve_lti_integration_by_client_id(client_id)
    if integration is None:
        return {
            "ok": False,
            "error": "invalid_client",
            "error_description": "Unknown or inactive client_id.",
            "status": 401,
        }
    cfg = integration.config or {}
    permitted = _normalize_scope_list(
        cfg.get("permitted_scopes")
        or cfg.get("lti_permitted_scopes")
        or integration.enabled_scopes
        or []
    )

    ok, reason, claims = _verify_tool_jwt_assertion(
        jwt_assertion=jwt_assertion,
        cfg=cfg,
        expected_audience=expected_audience or client_id,
    )
    if not ok:
        status = 401 if reason in {"bad_signature", "expired_assertion"} else 400
        if reason == "audience_mismatch":
            status = 401
        return {
            "ok": False,
            "error": "invalid_client" if status == 401 else "invalid_request",
            "error_description": f"client_assertion verification failed: {reason}",
            "status": status,
            "reason": reason,
        }

    granted = _intersect_scopes(requested, permitted)
    if requested and not granted:
        return {
            "ok": False,
            "error": "invalid_scope",
            "error_description": (
                "None of the requested scopes are permitted for this client."
            ),
            "status": 400,
        }

    # If caller asked for no scopes at all, grant the full permitted set
    # (defensible default — matches several real-world LTI platforms).
    final = granted if granted else list(permitted)

    now = int(time.time())
    jti = secrets.token_urlsafe(16)
    claims_out = {
        "iss": "https://runmycampus.com/lti",
        "sub": str(client_id),
        "aud": str(client_id),
        "iat": now,
        "exp": now + max(60, int(ttl_seconds)),
        "jti": jti,
        "scope": " ".join(final),
        "client_id": str(client_id),
        # Coerce to str so UUID / Decimal / etc. PKs serialize cleanly.
        "integration_id": str(integration.pk),
        "school_id": str(integration.school_id) if integration.school_id is not None else "",
        # Discard original assertion's claims except a couple breadcrumbs:
        "tool_assertion_iss": str(claims.get("iss") or "")[:200],
    }
    try:
        access_token = sign_platform_jwt(
            claims=claims_out,
            expires_in_seconds=ttl_seconds,
        )
    except Exception as exc:  # PlatformJWKSError or downstream
        logger.warning("LTI tool token sign failed: %s", exc)
        return {
            "ok": False,
            "error": "server_error",
            "error_description": "Unable to sign access token.",
            "status": 500,
        }
    logger.info(
        "LTI tool token issued client_id=%s integration_id=%s scope_count=%d",
        client_id,
        integration.pk,
        len(final),
    )
    return {
        "ok": True,
        "access_token": access_token,
        "token_type": "Bearer",
        "expires_in": int(ttl_seconds),
        "scope": " ".join(final),
        "client_id": str(client_id),
        "integration_id": str(integration.pk),
    }


# --- HTTP view ---------------------------------------------------------------


@csrf_exempt
@require_POST
def lti_tool_token_endpoint(request) -> HttpResponse:
    """``POST /lti/auth/token/`` — RFC 6749 § 4.4 client_credentials.

    Accepts form-urlencoded body per RFC-6749 § 3.2:
    ``grant_type=client_credentials&client_assertion_type=urn:ietf:params:
    oauth:client-assertion-type:jwt-bearer&client_assertion=<jwt>&scope=...``.

    Success (200): ``{access_token, token_type, expires_in, scope}``.
    Failure: RFC-6749 § 5.2 error envelope w/ ``error`` + ``error_description``.

    # rbac-allow: lti-tool-token-endpoint-anonymous-public-oauth-flow
    """
    grant_type = (request.POST.get("grant_type") or "").strip()
    assertion_type = (request.POST.get("client_assertion_type") or "").strip()
    jwt_assertion = (request.POST.get("client_assertion") or "").strip()
    scope = request.POST.get("scope") or ""
    client_id = (
        request.POST.get("client_id")
        or ""
    ).strip()

    if grant_type != GRANT_CLIENT_CREDENTIALS:
        return _oauth_error_response(
            "unsupported_grant_type",
            f"grant_type must be {GRANT_CLIENT_CREDENTIALS!r}",
            status=400,
        )
    if assertion_type != JWT_BEARER_ASSERTION_TYPE:
        return _oauth_error_response(
            "invalid_request",
            "client_assertion_type must be the JWT bearer URN.",
            status=400,
        )
    if not jwt_assertion:
        return _oauth_error_response(
            "invalid_request",
            "client_assertion is required.",
            status=400,
        )

    # client_id may live inside the JWT (iss/sub) when omitted from the form.
    if not client_id:
        try:
            _h, payload, _si, _s = _decode_jwt_segments(jwt_assertion)
            client_id = str(payload.get("iss") or payload.get("sub") or "").strip()
        except ValueError:
            return _oauth_error_response(
                "invalid_request",
                "client_assertion is not a parseable JWT.",
                status=400,
            )

    result = issue_lti_tool_access_token(
        client_id=client_id,
        requested_scopes=scope,
        jwt_assertion=jwt_assertion,
    )
    if not result.get("ok"):
        return _oauth_error_response(
            str(result.get("error") or "invalid_request"),
            str(result.get("error_description") or "Request failed."),
            status=int(result.get("status") or 400),
        )
    body = {
        "access_token": result["access_token"],
        "token_type": result["token_type"],
        "expires_in": result["expires_in"],
        "scope": result["scope"],
    }
    response = JsonResponse(body, status=200)
    response["Cache-Control"] = "no-store"
    response["Pragma"] = "no-cache"
    return response


def _oauth_error_response(
    error: str, description: str, *, status: int
) -> JsonResponse:
    response = JsonResponse(
        {"error": error, "error_description": description},
        status=status,
    )
    response["Cache-Control"] = "no-store"
    response["Pragma"] = "no-cache"
    return response


__all__ = [
    "DEFAULT_TOKEN_TTL_SECONDS",
    "GRANT_CLIENT_CREDENTIALS",
    "JWT_BEARER_ASSERTION_TYPE",
    "LTI_SCOPE_LINEITEM",
    "LTI_SCOPE_LINEITEM_RO",
    "LTI_SCOPE_NRPS_MEMBERSHIP",
    "LTI_SCOPE_RESULT_RO",
    "LTI_SCOPE_SCORE",
    "STANDARD_LTI_SCOPES",
    "issue_lti_tool_access_token",
    "lti_tool_token_endpoint",
]
