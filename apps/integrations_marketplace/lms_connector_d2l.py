"""v4.00.70 — Brightspace (D2L) LMS adapter scaffold.

Honest-stub adapter parallel to Schoology (v4.00.69) — registered in
``lms_supported_providers.SCAFFOLD_LMS_PROVIDERS`` but NOT in the
OAuth-ready set yet. The functions here are import-stable and have the
correct return shape contracts so calling code can be written against
them; production wiring (real HTTP calls, OAuth exchange) lands in a
follow-up wave once the integration partner test instance is provisioned.

Public surface (mirrors ``apps.api.lms_adapters`` for canvas/moodle/google):

  * ``oauth_authorize_url(*, client_id, redirect_uri, state, scopes=()) -> str``
  * ``refresh_token(*, refresh_token, client_id, client_secret) -> dict``
  * ``push_grade(*, base_url, access_token, course_id, user_id, score, max_score) -> dict``
  * ``pull_courses(*, base_url, access_token) -> list[dict]``

Honest stubs return either an empty success shape (so plumbing tests pass)
or ``{"ok": False, "reason": "scaffold_not_wired"}`` when production
behavior is required. The diagnostics dashboard surfaces a "Scaffold"
pill so operators know not to attempt connection grants yet.

Brightspace API specifics (per Valence Learning Platform docs):
* OAuth2 authorize URL: ``https://auth.brightspace.com/oauth2/auth``
* Token URL: ``https://auth.brightspace.com/core/connect/token``
* Default scopes: ``core:*:* grades:*:read grades:*:write enrollment:*:read``
"""
from __future__ import annotations

import logging
import urllib.parse as _ulib

logger = logging.getLogger(__name__)

# Per Brightspace Valence OAuth2 docs (Apr 2026 snapshot).
DEFAULT_AUTHORIZE_URL = "https://auth.brightspace.com/oauth2/auth"
DEFAULT_TOKEN_URL = "https://auth.brightspace.com/core/connect/token"
DEFAULT_SCOPES = (
    "core:*:*",
    "grades:*:read",
    "grades:*:write",
    "enrollment:*:read",
)

PROVIDER_SLUG = "d2l_brightspace"
PROVIDER_LABEL = "Brightspace (D2L)"

# v4.00.72 — OAuth state mint TimestampSigner salt + TTL.
OAUTH_STATE_SALT = "rmc.lms.d2l_brightspace.oauth_state.v4.00.72"
OAUTH_STATE_TTL_SECONDS = 600  # 10 min


def oauth_authorize_url(
    *,
    client_id: str,
    redirect_uri: str,
    state: str,
    scopes: tuple = DEFAULT_SCOPES,
    authorize_url: str = DEFAULT_AUTHORIZE_URL,
) -> str:
    """Build the Brightspace OAuth2 authorize URL. Caller must vault
    ``state`` server-side to defend against CSRF."""
    qs = _ulib.urlencode([
        ("response_type", "code"),
        ("client_id", client_id),
        ("redirect_uri", redirect_uri),
        ("state", state),
        ("scope", " ".join(scopes)),
    ])
    sep = "&" if "?" in authorize_url else "?"
    return f"{authorize_url}{sep}{qs}"


def mint_oauth_state(*, tenant_slug: str, user_pk: str | int,
                      redirect_path: str = "/") -> str:
    """v4.00.72 — Mint a CSRF-safe OAuth state signed w/ TimestampSigner.
    Payload format: ``"<tenant_slug>:<user_pk>:<redirect_path>"``.
    Open-redirect defense: redirect_path must start with "/" not "//".
    """
    from django.core.signing import TimestampSigner
    signer = TimestampSigner(salt=OAUTH_STATE_SALT)
    safe_redirect = redirect_path if redirect_path.startswith("/") and not redirect_path.startswith("//") else "/"
    payload = f"{tenant_slug}:{user_pk}:{safe_redirect}"
    return signer.sign(payload)


def read_oauth_state(raw: str):
    """v4.00.72 — Return ``(parsed_dict_or_None, reason)``. 5-state taxonomy."""
    from django.core.signing import TimestampSigner, BadSignature, SignatureExpired
    signer = TimestampSigner(salt=OAUTH_STATE_SALT)
    if not raw:
        return None, "missing_token"
    try:
        payload = signer.unsign(raw, max_age=OAUTH_STATE_TTL_SECONDS)
    except SignatureExpired:
        return None, "expired_token"
    except BadSignature:
        return None, "bad_token"
    parts = payload.split(":", 2)
    if len(parts) != 3:
        return None, "malformed_payload"
    return {"tenant_slug": parts[0], "user_pk": parts[1],
            "redirect_path": parts[2]}, "ok"


def refresh_token(*, refresh_token: str, client_id: str, client_secret: str) -> dict:
    """Honest-stub. Returns scaffold_not_wired to make the contract loud."""
    logger.info("d2l_brightspace.refresh_token: scaffold call (not wired)")
    return {"ok": False, "reason": "scaffold_not_wired",
            "provider": PROVIDER_SLUG, "wave_landed": "v4.00.70"}


def push_grade(*, base_url: str, access_token: str, course_id: str,
               user_id: str, score: float, max_score: float,
               grade_object_id: str = "", api_version: str = "1.66",
               comment: str = "") -> dict:
    """v4.00.76 — Honest-stub. Real wiring requires Brightspace GradeObjects
    + GradeValues endpoints + a pre-flight ``GET /d2l/api/le/<version>/orgUnit/<id>``
    to confirm the orgUnit's grading scheme.

    Returns the intended request shape under ``would_send`` so caller code
    can unit-test payload assembly without hitting the network. Local
    validation mirrors v4.00.75 Schoology push_grade so callers can rely
    on identical error reason taxonomy across providers.
    """
    if not course_id or not user_id:
        return {"ok": False, "reason": "missing_required_field",
                "provider": PROVIDER_SLUG, "field": "course_id_or_user_id"}
    try:
        s = float(score)
        m = float(max_score)
    except (ValueError, TypeError):
        return {"ok": False, "reason": "score_not_numeric",
                "provider": PROVIDER_SLUG}
    if s < 0 or m <= 0:
        return {"ok": False, "reason": "score_out_of_range",
                "provider": PROVIDER_SLUG, "score": s, "max_score": m}
    if s > m:
        return {"ok": False, "reason": "score_exceeds_max",
                "provider": PROVIDER_SLUG, "score": s, "max_score": m}

    # Brightspace API: PUT /d2l/api/le/<ver>/<orgUnitId>/grades/<gradeObjId>/values/<userId>
    endpoint = (
        f"{base_url.rstrip('/')}/d2l/api/le/{api_version}/{course_id}"
        f"/grades/{grade_object_id or 'unknown'}/values/{user_id}"
    )
    payload_shape = {
        "endpoint": endpoint,
        "method": "PUT",
        "body": {
            "GradeObjectType": 1,  # 1 = Numeric grade per Brightspace docs
            "PointsNumerator": s,
            "PointsDenominator": m,
            "Comments": {"Content": comment, "Type": "Text"} if comment else None,
        },
    }
    logger.info("d2l_brightspace.push_grade: scaffold call (would send %s)", endpoint)
    return {"ok": False, "reason": "scaffold_not_wired",
            "provider": PROVIDER_SLUG, "course_id": course_id, "user_id": user_id,
            "would_send": payload_shape}


def pull_courses(*, base_url: str, access_token: str) -> list[dict]:
    """Honest-stub. Real implementation walks
    ``GET /d2l/api/lp/<version>/enrollments/myenrollments/`` and resolves
    each orgUnit by ID."""
    logger.info("d2l_brightspace.pull_courses: scaffold call (not wired)")
    return []


def is_scaffold() -> bool:
    # v4.00.84 — D2L Brightspace promoted to OAUTH_READY in
    # lms_supported_providers. Kept returning False so callers checking the
    # adapter directly see the current maturity. The honest-stub push_grade
    # above remains for dry-run consumers; live outbound is gated by
    # ``push_grade_live`` + env flag.
    return False


# ---------------------------------------------------------------------------
# v4.00.84 — Live OAuth code-exchange + push_grade_live (gated behind env flag).
# v4.00.89 — Audit-hook + refresh-token flow + retry-with-backoff.
# ---------------------------------------------------------------------------
import hashlib as _hashlib
import os
import logging
import time as _time
from typing import Any, Callable

logger = logging.getLogger(__name__)

LIVE_OUTBOUND_ENV = "RMC_D2L_OAUTH_LIVE_OUTBOUND"

# D2L Brightspace Valence API version anchor. Bump as Brightspace publishes
# new minor versions of the LE (Learning Environment) product API.
_DEFAULT_API_VERSION = "1.46"

# Retry / backoff constants (v4.00.89). v4.00.90 — 429 added (rate-limit)
# but only when Retry-After header is parseable; bare-429 without that
# hint stays terminal.
_RETRY_HTTP_STATUSES = frozenset({502, 503, 504})
_RETRY_RATE_LIMIT_STATUS = 429
_RETRY_BACKOFF_CAP_SECONDS = 8.0
_RETRY_AFTER_CAP_SECONDS = 60.0


def _live_outbound_enabled() -> bool:
    return os.environ.get(LIVE_OUTBOUND_ENV, "") in ("1", "true", "yes", "on")


def _short_hash(value: str) -> str:
    """SHA-256[:12] of arbitrary string — used for token correlation in
    audit rows WITHOUT leaking the underlying secret. Empty input -> ""."""
    if not value:
        return ""
    return _hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]


def _record_audit(*, action: str, provider: str, ok: bool,
                  http_status: int = 0, reason: str = "",
                  tenant_schema: str = "",
                  payload_summary: dict | None = None) -> None:
    """v4.00.89 — Persist an audit row for an OAuth exchange / push_grade
    invocation. Wraps the existing ``LMSDiagActionAudit`` SOT model so we
    don't fork audit storage. NEVER raises. NEVER logs secret-class fields."""
    _FORBIDDEN_KEYS = (
        "client_secret", "access_token", "refresh_token", "code",
        "password", "passwd", "pwd", "api_key", "apikey", "private_key",
        "signature_text",
    )
    safe_summary: dict[str, Any] = {}
    if payload_summary:
        for k, v in payload_summary.items():
            k_lc = str(k).lower()
            if any(bad in k_lc for bad in _FORBIDDEN_KEYS):
                continue
            safe_summary[str(k)] = v
    try:
        from apps.integrations_marketplace.models import LMSDiagActionAudit
        actor_hash = _short_hash(tenant_schema) if tenant_schema else ""
        LMSDiagActionAudit.objects.create(  # tenant-isolation-allow: lms-oauth-outbound-audit-platform-scope-staff-only
            action=action[:32],
            provider=provider[:24],
            actor_hash=actor_hash,
            actor_user_id="",
            considered=int(http_status or 0),
            ok_count=1 if ok else 0,
            failed_count=0 if ok else 1,
        )
    except Exception as exc:  # noqa: BLE001
        logger.debug("d2l_brightspace._record_audit DB persist failed: %s",
                     type(exc).__name__)
    try:
        logger.info(
            "lms_oauth_audit provider=%s action=%s ok=%s http=%s reason=%s "
            "tenant_hash=%s summary_keys=%s",
            provider, action, ok, http_status, reason,
            _short_hash(tenant_schema), sorted(safe_summary.keys()),
        )
    except Exception:  # noqa: BLE001
        pass


def _retry_with_backoff(call: Callable[[], Any], *,
                        max_attempts: int = 3,
                        base_delay: float = 1.0) -> Any:
    """v4.00.89 — Same semantics as the Schoology helper (duplicated by
    design — small enough to avoid forking a shared module).

    Retries on ``requests.Timeout`` / ``requests.ConnectionError`` and
    HTTP 502/503/504. Exponential backoff: 1s, 2s, 4s (capped at 8s).
    Does NOT retry on 4xx, 2xx, or non-network exceptions.
    """
    try:
        import requests
        _Timeout = requests.Timeout
        _ConnErr = requests.ConnectionError
    except ImportError:
        return call()

    last_exc: BaseException | None = None
    for attempt in range(max(1, int(max_attempts))):
        try:
            resp = call()
        except (_Timeout, _ConnErr) as exc:
            last_exc = exc
            if attempt + 1 >= max_attempts:
                raise
            delay = min(base_delay * (2 ** attempt), _RETRY_BACKOFF_CAP_SECONDS)
            _time.sleep(delay)
            continue
        status = getattr(resp, "status_code", None)
        if status in _RETRY_HTTP_STATUSES and attempt + 1 < max_attempts:
            delay = min(base_delay * (2 ** attempt), _RETRY_BACKOFF_CAP_SECONDS)
            _time.sleep(delay)
            continue
        # v4.00.90 — honor Retry-After on 429.
        if status == _RETRY_RATE_LIMIT_STATUS and attempt + 1 < max_attempts:
            from apps.integrations_marketplace.oauth_live_path_helpers import (
                parse_retry_after as _parse_retry_after,
            )
            ra = None
            headers = getattr(resp, "headers", None)
            if headers is not None:
                try:
                    ra = _parse_retry_after(headers.get("Retry-After"))
                except Exception:  # noqa: BLE001
                    ra = None
            if ra is not None:
                _time.sleep(min(ra, _RETRY_AFTER_CAP_SECONDS))
                continue
        return resp
    if last_exc is not None:
        raise last_exc
    return None


def exchange_authorization_code_for_token(*, code: str, client_id: str,
                                          client_secret: str,
                                          redirect_uri: str,
                                          token_url: str = DEFAULT_TOKEN_URL,
                                          timeout: int = 15,
                                          tenant_schema: str = "") -> dict:
    """Exchange an OAuth authorization code for an access token against
    Brightspace's ``/core/connect/token`` endpoint.

    When LIVE_OUTBOUND_ENV is unset (default), returns a dry-run dict that
    looks like a Brightspace success response.

    On real outbound: returns the upstream JSON OR a structured error dict
    if the upstream returned non-2xx / network error. NEVER raises.

    NEVER logs client_secret / access_token / refresh_token (PII guard).
    """
    if not code or not client_id or not client_secret or not redirect_uri:
        result = {"dry_run": False, "ok": False, "reason": "validation_error",
                  "missing_field": True}
        _record_audit(action="oauth_exchange", provider=PROVIDER_SLUG,
                      ok=False, http_status=0, reason="validation_error",
                      tenant_schema=tenant_schema,
                      payload_summary={"missing_field": True})
        return result

    if not _live_outbound_enabled():
        return {
            "access_token": "dry-run-access-token",
            "refresh_token": "dry-run-refresh-token",
            "expires_in": 3600,
            "token_type": "Bearer",
            "scope": " ".join(DEFAULT_SCOPES) if DEFAULT_SCOPES else "",
            "dry_run": True,
            "ok": False,
            "reason": "live_outbound_disabled_env_unset",
            "target_url": token_url,
        }
    try:
        import requests
    except ImportError:
        return {"dry_run": False, "ok": False, "reason": "requests_lib_missing"}

    def _do_post() -> Any:
        return requests.post(
            token_url,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "client_id": client_id,
                "client_secret": client_secret,
                "redirect_uri": redirect_uri,
            },
            headers={"Accept": "application/json"},
            timeout=timeout,
        )

    try:
        resp = _retry_with_backoff(_do_post)
    except Exception as exc:  # noqa: BLE001
        logger.warning("d2l_brightspace token exchange network error: %s",
                       type(exc).__name__)
        result = {"dry_run": False, "ok": False, "reason": "network_error",
                  "exc_type": type(exc).__name__}
        _record_audit(action="oauth_exchange", provider=PROVIDER_SLUG,
                      ok=False, http_status=0, reason="network_error",
                      tenant_schema=tenant_schema,
                      payload_summary={"exc_type": type(exc).__name__})
        return result

    status = getattr(resp, "status_code", 0)
    if not (200 <= status < 300):
        # v4.00.90 — RFC-6749 § 5.2 error decode.
        from apps.integrations_marketplace.oauth_live_path_helpers import (
            decode_oauth2_error_response as _decode_err,
        )
        try:
            err_body = resp.json()
        except Exception:  # noqa: BLE001
            err_body = None
        decoded = _decode_err(err_body)
        logger.warning("d2l_brightspace token exchange http_%s code=%s",
                       status, decoded.get("error_code"))
        result = {"dry_run": False, "ok": False, "reason": "upstream_error",
                  "http_status": status,
                  "oauth_error_code": decoded.get("error_code"),
                  "oauth_error_description": decoded.get("error_description")}
        _record_audit(action="oauth_exchange", provider=PROVIDER_SLUG,
                      ok=False, http_status=status, reason="upstream_error",
                      tenant_schema=tenant_schema,
                      payload_summary={"http_status": status,
                                       "oauth_error_code": decoded.get("error_code")})
        return result

    try:
        body = resp.json()
    except Exception:  # noqa: BLE001
        result = {"dry_run": False, "ok": False, "reason": "upstream_error",
                  "http_status": status, "detail": "json_parse_error"}
        _record_audit(action="oauth_exchange", provider=PROVIDER_SLUG,
                      ok=False, http_status=status, reason="upstream_error",
                      tenant_schema=tenant_schema,
                      payload_summary={"http_status": status,
                                       "detail": "json_parse_error"})
        return result

    body["dry_run"] = False
    body["ok"] = True
    # v4.00.90 — Issue timestamp so background refresh sweep can call
    # is_token_expired().
    from datetime import datetime as _dt, timezone as _tz
    body.setdefault("issued_at_iso",
                    _dt.now(_tz.utc).replace(microsecond=0).isoformat())
    _at_hash = _short_hash(str(body.get("access_token") or ""))
    _rt_hash = _short_hash(str(body.get("refresh_token") or ""))
    _record_audit(action="oauth_exchange", provider=PROVIDER_SLUG,
                  ok=True, http_status=status, reason="ok",
                  tenant_schema=tenant_schema,
                  payload_summary={"http_status": status,
                                   "access_token_hash": _at_hash,
                                   "refresh_token_hash": _rt_hash,
                                   "expires_in": body.get("expires_in")})
    return body


def refresh_access_token(*, refresh_token: str, client_id: str,
                         client_secret: str,
                         token_url: str = DEFAULT_TOKEN_URL,
                         timeout: int = 15,
                         tenant_schema: str = "") -> dict:
    """v4.00.89 — Refresh a D2L Brightspace OAuth access token.

    Same env-gate + dry-run pattern as
    ``exchange_authorization_code_for_token``. POSTs
    ``grant_type=refresh_token&refresh_token=<rt>&client_id=<id>&client_secret=<secret>``
    to ``/d2l/auth/api/token`` (mapped onto ``DEFAULT_TOKEN_URL`` by default —
    Brightspace's identity service publishes both paths against the same
    upstream). NEVER logs client_secret / refresh_token.
    """
    if not refresh_token or not client_id or not client_secret:
        result = {"dry_run": False, "ok": False, "reason": "validation_error",
                  "missing_field": True}
        _record_audit(action="oauth_refresh", provider=PROVIDER_SLUG,
                      ok=False, http_status=0, reason="validation_error",
                      tenant_schema=tenant_schema,
                      payload_summary={"missing_field": True})
        return result

    if not _live_outbound_enabled():
        return {
            "access_token": "dry-run-refreshed-access-token",
            "refresh_token": "dry-run-refreshed-refresh-token",
            "expires_in": 3600,
            "token_type": "Bearer",
            "scope": " ".join(DEFAULT_SCOPES) if DEFAULT_SCOPES else "",
            "dry_run": True,
            "ok": False,
            "reason": "live_outbound_disabled_env_unset",
            "target_url": token_url,
        }
    try:
        import requests
    except ImportError:
        return {"dry_run": False, "ok": False, "reason": "requests_lib_missing"}

    def _do_post() -> Any:
        return requests.post(
            token_url,
            data={
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "client_id": client_id,
                "client_secret": client_secret,
            },
            headers={"Accept": "application/json"},
            timeout=timeout,
        )

    try:
        resp = _retry_with_backoff(_do_post)
    except Exception as exc:  # noqa: BLE001
        logger.warning("d2l_brightspace token refresh network error: %s",
                       type(exc).__name__)
        result = {"dry_run": False, "ok": False, "reason": "network_error",
                  "exc_type": type(exc).__name__}
        _record_audit(action="oauth_refresh", provider=PROVIDER_SLUG,
                      ok=False, http_status=0, reason="network_error",
                      tenant_schema=tenant_schema,
                      payload_summary={"exc_type": type(exc).__name__})
        return result

    status = getattr(resp, "status_code", 0)
    if not (200 <= status < 300):
        # v4.00.90 — RFC-6749 § 5.2 error decode.
        from apps.integrations_marketplace.oauth_live_path_helpers import (
            decode_oauth2_error_response as _decode_err,
        )
        try:
            err_body = resp.json()
        except Exception:  # noqa: BLE001
            err_body = None
        decoded = _decode_err(err_body)
        logger.warning("d2l_brightspace token refresh http_%s code=%s",
                       status, decoded.get("error_code"))
        result = {"dry_run": False, "ok": False, "reason": "upstream_error",
                  "http_status": status,
                  "oauth_error_code": decoded.get("error_code"),
                  "oauth_error_description": decoded.get("error_description")}
        _record_audit(action="oauth_refresh", provider=PROVIDER_SLUG,
                      ok=False, http_status=status, reason="upstream_error",
                      tenant_schema=tenant_schema,
                      payload_summary={"http_status": status,
                                       "oauth_error_code": decoded.get("error_code")})
        return result

    try:
        body = resp.json()
    except Exception:  # noqa: BLE001
        result = {"dry_run": False, "ok": False, "reason": "upstream_error",
                  "http_status": status, "detail": "json_parse_error"}
        _record_audit(action="oauth_refresh", provider=PROVIDER_SLUG,
                      ok=False, http_status=status, reason="upstream_error",
                      tenant_schema=tenant_schema,
                      payload_summary={"http_status": status,
                                       "detail": "json_parse_error"})
        return result

    body["dry_run"] = False
    body["ok"] = True
    from datetime import datetime as _dt, timezone as _tz
    body.setdefault("issued_at_iso",
                    _dt.now(_tz.utc).replace(microsecond=0).isoformat())
    _at_hash = _short_hash(str(body.get("access_token") or ""))
    _rt_hash = _short_hash(str(body.get("refresh_token") or ""))
    _record_audit(action="oauth_refresh", provider=PROVIDER_SLUG,
                  ok=True, http_status=status, reason="ok",
                  tenant_schema=tenant_schema,
                  payload_summary={"http_status": status,
                                   "access_token_hash": _at_hash,
                                   "refresh_token_hash": _rt_hash,
                                   "expires_in": body.get("expires_in")})
    return body


def push_grade_live(*, access_token: str, org_unit_id: str,
                    grade_object_id: str, user_id: str,
                    score: float, max_score: float, comment: str = "",
                    api_base: str = "https://your-tenant.brightspace.com",
                    api_version: str = _DEFAULT_API_VERSION,
                    timeout: int = 15,
                    tenant_schema: str = "") -> dict:
    """REAL outbound push_grade against D2L Brightspace's
    ``PUT /d2l/api/le/<ver>/<orgUnit>/grades/<gradeObj>/values/<user>``
    endpoint. Gated behind LIVE_OUTBOUND_ENV. Returns upstream JSON on
    success, structured error dict on failure. NEVER raises."""
    target = (
        f"{api_base.rstrip('/')}/d2l/api/le/{api_version}/{org_unit_id}"
        f"/grades/{grade_object_id}/values/{user_id}"
    )
    if not _live_outbound_enabled():
        return {
            "ok": False,
            "dry_run": True,
            "reason": "live_outbound_disabled_env_unset",
            "would_target": target,
            "target_url": target,
        }
    try:
        import requests
    except ImportError:
        return {"ok": False, "dry_run": False, "reason": "requests_lib_missing"}

    payload = {
        "PointsNumerator": float(score),
        "Comments": {"Content": comment[:1000], "Type": "Text"},
    }
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    def _do_put() -> Any:
        return requests.put(target, json=payload, headers=headers,
                            timeout=timeout)

    try:
        resp = _retry_with_backoff(_do_put)
    except Exception as exc:  # noqa: BLE001
        result = {"ok": False, "dry_run": False, "reason": "network_error",
                  "exc_type": type(exc).__name__}
        _record_audit(action="push_grade_live", provider=PROVIDER_SLUG,
                      ok=False, http_status=0, reason="network_error",
                      tenant_schema=tenant_schema,
                      payload_summary={"exc_type": type(exc).__name__,
                                       "org_unit_id": org_unit_id,
                                       "grade_object_id": grade_object_id})
        return result

    status = getattr(resp, "status_code", 0)
    if not (200 <= status < 300):
        result = {"ok": False, "dry_run": False, "reason": "upstream_error",
                  "http_status": status}
        _record_audit(action="push_grade_live", provider=PROVIDER_SLUG,
                      ok=False, http_status=status, reason="upstream_error",
                      tenant_schema=tenant_schema,
                      payload_summary={"http_status": status,
                                       "org_unit_id": org_unit_id,
                                       "grade_object_id": grade_object_id})
        return result

    try:
        upstream_body = resp.json()
    except Exception:  # noqa: BLE001
        upstream_body = None
    result = {"ok": True, "dry_run": False, "http_status": status}
    if upstream_body is not None:
        result["upstream"] = upstream_body
    _record_audit(action="push_grade_live", provider=PROVIDER_SLUG,
                  ok=True, http_status=status, reason="ok",
                  tenant_schema=tenant_schema,
                  payload_summary={"http_status": status,
                                   "org_unit_id": org_unit_id,
                                   "grade_object_id": grade_object_id,
                                   "user_id_hash": _short_hash(user_id)})
    return result
