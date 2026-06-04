"""v4.00.92 Wave 25 C4 — OneRoster v1.2 OAuth2 client_credentials grant.

Implements RFC 6749 § 4.4 (Client Credentials Grant) for the OneRoster
v1.2 inbound API. Backwards-compatible with the legacy static Bearer
token in ``RMC_ONEROSTER_ACCESS_TOKEN``: the bearer validator in
``oneroster._authenticate`` is extended to accept BOTH static-env tokens
AND tokens minted here.

Storage contract for client_id / client_secret
----------------------------------------------
Env: ``RMC_ONEROSTER_OAUTH_CLIENTS`` = JSON-encoded dict of the form

    {
        "<client_id>": {
            "secret_hash": "<sha256 hex digest, lowercase>",
            "allowed_scopes": ["roster-core.readonly", ...],
            "tenant_schema": "<tenant_schema_name>"
        },
        ...
    }

``secret_hash`` is ``sha256(secret).hexdigest()`` of the operator's
chosen raw secret. The raw secret is NEVER stored or logged. Comparison
uses :func:`hmac.compare_digest` against the hashed value to defeat
timing-attack reconnaissance.

Public surface
--------------
:func:`issue_oneroster_access_token` (programmatic):
    Validates a client_credentials request and returns either the
    access-token envelope or an RFC 6749 § 5.2 error envelope.

:func:`oneroster_token_endpoint` (HTTP view):
    POST /api/roster/v1p2/oauth/token/
    Form-encoded body: ``grant_type=client_credentials&client_id=...
    &client_secret=...&scope=<space-sep>``.

:func:`decode_oauth2_bearer_token` (helper):
    Decodes a signed token issued here. Returns
    ``(ok: bool, payload: dict | None)``. Used by the Bearer auth path
    in :mod:`apps.api.oneroster` to recognize OAuth2-issued tokens
    alongside the legacy static env token.

Token format
------------
Signed via :class:`django.core.signing.TimestampSigner` with
salt ``rmc.oneroster.v1p2.access_token.v4.00.92``. Payload:

    "<client_id>:<tenant_schema>:<space-separated-granted-scopes>"

Quality bars
------------
* Never logs ``client_secret`` or the raw token bytes.
* Constant-time secret comparison.
* Returns RFC 6749 § 5.2 error codes: ``invalid_client``,
  ``invalid_scope``, ``invalid_request``, ``unsupported_grant_type``.
* IMS-standard scope vocabulary: ``roster-core.readonly`` /
  ``roster-core.createput`` / ``roster-demographics.readonly`` /
  ``roster-demographics.createput`` / ``roster-results.readonly`` /
  ``roster-results.createput``.
"""
from __future__ import annotations

import hashlib
import hmac
import json as _json
import logging
import os
from typing import Any

from django.conf import settings
from django.core.signing import BadSignature, SignatureExpired, TimestampSigner
from django.http import HttpRequest, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_SIGNER_SALT = "rmc.oneroster.v1p2.access_token.v4.00.92"
_TOKEN_TTL_SECONDS = 3600  # magic-number-allow: ttl-seconds
_SUPPORTED_GRANT_TYPE = "client_credentials"

# IMS-standard OneRoster v1.2 scope vocabulary. New scopes added here MUST
# also be reflected in the per-endpoint scope-requirement table consumed by
# ``oneroster._authenticate``.
IMS_ROSTER_SCOPES: frozenset[str] = frozenset({
    "roster-core.readonly",
    "roster-core.createput",
    "roster-demographics.readonly",
    "roster-demographics.createput",
    "roster-results.readonly",
    "roster-results.createput",
})


# ---------------------------------------------------------------------------
# Client registry resolution
# ---------------------------------------------------------------------------


def _resolve_clients_registry() -> dict[str, dict[str, Any]]:
    """Read + parse the env-encoded client registry.

    Returns an empty dict on missing / malformed env so the token endpoint
    can return ``invalid_client`` rather than crashing.
    """
    raw = (
        getattr(settings, "RMC_ONEROSTER_OAUTH_CLIENTS", "")
        or os.environ.get("RMC_ONEROSTER_OAUTH_CLIENTS", "")
        or ""
    )
    if not raw:
        return {}
    try:
        parsed = _json.loads(raw)
    except (ValueError, TypeError):
        logger.warning("oneroster oauth2: client registry env is not valid JSON")
        return {}
    if not isinstance(parsed, dict):
        logger.warning("oneroster oauth2: client registry env is not a JSON object")
        return {}
    # Defensive: coerce each entry into a known shape (drop malformed rows).
    out: dict[str, dict[str, Any]] = {}
    for cid, row in parsed.items():
        if not isinstance(cid, str) or not isinstance(row, dict):
            continue
        secret_hash = str(row.get("secret_hash") or "").strip().lower()
        if not secret_hash:
            continue
        allowed = row.get("allowed_scopes")
        if not isinstance(allowed, list):
            allowed = []
        tenant_schema = str(row.get("tenant_schema") or "").strip()
        out[cid] = {
            "secret_hash": secret_hash,
            "allowed_scopes": [str(s).strip() for s in allowed if s],
            "tenant_schema": tenant_schema,
        }
    return out


def _hash_secret(raw_secret: str) -> str:
    """SHA-256 hex digest of the raw secret (lowercase)."""
    h = hashlib.sha256()
    h.update((raw_secret or "").encode("utf-8"))
    return h.hexdigest()


# ---------------------------------------------------------------------------
# Token signing / verification
# ---------------------------------------------------------------------------


def _signer() -> TimestampSigner:
    return TimestampSigner(salt=_SIGNER_SALT)


def _encode_access_token(*, client_id: str, tenant_schema: str, granted_scopes: list[str]) -> str:
    """Return a signed Bearer-token string."""
    payload = f"{client_id}:{tenant_schema}:{' '.join(granted_scopes)}"
    return _signer().sign(payload)


def decode_oauth2_bearer_token(token: str, *, max_age: int = _TOKEN_TTL_SECONDS) -> tuple[bool, dict[str, Any] | None]:
    """Decode a signed Bearer token issued by this module.

    Returns ``(ok, payload_dict)`` where ``payload_dict`` carries
    ``client_id``, ``tenant_schema``, ``scopes`` (list[str]).
    Returns ``(False, None)`` on expired / tampered / non-OAuth2 tokens
    (e.g. the legacy static token — caller should fall through).
    """
    if not token:
        return False, None
    try:
        unsigned = _signer().unsign(token, max_age=max_age)
    except SignatureExpired:
        return False, None
    except BadSignature:
        return False, None
    except (ValueError, TypeError):
        return False, None
    # Payload shape: "<client_id>:<tenant_schema>:<scopes>"
    parts = unsigned.split(":", 2)
    if len(parts) != 3:
        return False, None
    client_id, tenant_schema, scopes_str = parts
    scopes = [s for s in scopes_str.split(" ") if s]
    return True, {
        "client_id": client_id,
        "tenant_schema": tenant_schema,
        "scopes": scopes,
    }


# ---------------------------------------------------------------------------
# Programmatic issuance
# ---------------------------------------------------------------------------


def issue_oneroster_access_token(
    *,
    client_id: str,
    client_secret: str,
    requested_scopes: list[str],
    tenant_schema: str = "",
) -> dict[str, Any]:
    """Validate a client_credentials request and mint an access token.

    Returns one of:

      * Success: ``{access_token, token_type: "Bearer", expires_in,
        scope, ok: True}``.
      * Failure: ``{ok: False, error: "<rfc6749 code>"}``.

    The ``tenant_schema`` kwarg is informational — the canonical schema
    comes from the client registry row. Callers that supply a value get
    it back in the audit log only when it matches the registry; mismatch
    is silently ignored (the registry wins).
    """
    if not client_id or not isinstance(client_id, str):
        return {"ok": False, "error": "invalid_request"}
    if not client_secret or not isinstance(client_secret, str):
        return {"ok": False, "error": "invalid_request"}

    registry = _resolve_clients_registry()
    row = registry.get(client_id)
    if row is None:
        # Don't reveal whether the client_id was missing vs the secret was
        # wrong — RFC 6749 § 5.2 says both map to ``invalid_client``.
        return {"ok": False, "error": "invalid_client"}

    submitted_hash = _hash_secret(client_secret)
    stored_hash = str(row.get("secret_hash") or "").lower()
    # Constant-time compare to defeat timing-attack reconnaissance.
    if not stored_hash or not hmac.compare_digest(submitted_hash, stored_hash):
        return {"ok": False, "error": "invalid_client"}

    allowed = set(row.get("allowed_scopes") or [])
    if not allowed:
        # Misconfigured registry row — fail closed.
        return {"ok": False, "error": "invalid_scope"}

    # Filter requested scopes to those the client is allowed to use.
    # An empty request grants the intersection of the client's allowed
    # set with the IMS vocab (default downscope when caller omits scope).
    requested_clean = [s.strip() for s in (requested_scopes or []) if s and s.strip()]
    if not requested_clean:
        granted = sorted(allowed & IMS_ROSTER_SCOPES)
    else:
        # Reject any unknown / non-IMS scope per RFC 6749 § 3.3.
        for s in requested_clean:
            if s not in IMS_ROSTER_SCOPES:
                return {"ok": False, "error": "invalid_scope"}
        granted = sorted(s for s in requested_clean if s in allowed)
    if not granted:
        return {"ok": False, "error": "invalid_scope"}

    registry_tenant = str(row.get("tenant_schema") or tenant_schema or "")
    token = _encode_access_token(
        client_id=client_id,
        tenant_schema=registry_tenant,
        granted_scopes=granted,
    )
    return {
        "ok": True,
        "access_token": token,
        "token_type": "Bearer",
        "expires_in": _TOKEN_TTL_SECONDS,
        "scope": " ".join(granted),
        "tenant_schema": registry_tenant,
    }


# ---------------------------------------------------------------------------
# HTTP view
# ---------------------------------------------------------------------------


def _read_token_request_field(request: HttpRequest, key: str) -> str:
    """Read a field from form-encoded POST body OR JSON body OR querystring.

    RFC 6749 § 4.4.2 mandates form-encoded body, but operator tooling in
    the wild routinely sends JSON. We accept both for robustness, and
    fall through to querystring only as a last resort (never preferred).
    """
    val = (request.POST.get(key) or "").strip()
    if val:
        return val
    if request.content_type and request.content_type.startswith("application/json"):
        try:
            body = _json.loads(request.body or b"{}")
            if isinstance(body, dict):
                v = body.get(key)
                if isinstance(v, str) and v.strip():
                    return v.strip()
        except (ValueError, TypeError):
            pass
    val = (request.GET.get(key) or "").strip()
    return val


def _error_response(*, error: str, status: int) -> JsonResponse:
    """RFC 6749 § 5.2 error envelope."""
    resp = JsonResponse({"error": error}, status=status)
    resp["Cache-Control"] = "no-store"
    resp["Pragma"] = "no-cache"
    return resp


@csrf_exempt
@require_http_methods(["POST"])
def oneroster_token_endpoint(request: HttpRequest):
    """v4.00.92 Wave 25 C4 — POST /api/roster/v1p2/oauth/token/.

    RFC 6749 § 4.4 client_credentials grant. Returns
    ``application/json`` with the standard OAuth2 token envelope on
    success and RFC 6749 § 5.2 error codes on failure.
    """
    grant_type = _read_token_request_field(request, "grant_type")
    if not grant_type:
        return _error_response(error="invalid_request", status=400)
    if grant_type != _SUPPORTED_GRANT_TYPE:
        return _error_response(error="unsupported_grant_type", status=400)

    client_id = _read_token_request_field(request, "client_id")
    client_secret = _read_token_request_field(request, "client_secret")
    if not client_id or not client_secret:
        return _error_response(error="invalid_request", status=400)

    scope = _read_token_request_field(request, "scope")
    requested_scopes = [s for s in scope.split(" ") if s] if scope else []

    result = issue_oneroster_access_token(
        client_id=client_id,
        client_secret=client_secret,
        requested_scopes=requested_scopes,
    )
    if not result.get("ok"):
        err = str(result.get("error") or "invalid_request")
        # invalid_client per RFC 6749 § 5.2 uses 401 + WWW-Authenticate.
        if err == "invalid_client":
            resp = _error_response(error=err, status=401)
            resp["WWW-Authenticate"] = 'Basic realm="OneRoster v1.2"'
            return resp
        return _error_response(error=err, status=400)

    body = {
        "access_token": result["access_token"],
        "token_type": result["token_type"],
        "expires_in": result["expires_in"],
        "scope": result["scope"],
    }
    resp = JsonResponse(body, status=200)
    resp["Cache-Control"] = "no-store"
    resp["Pragma"] = "no-cache"
    return resp
