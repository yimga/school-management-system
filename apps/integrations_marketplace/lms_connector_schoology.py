"""v4.00.71 — Schoology LMS adapter scaffold (parallel to v4.00.70 D2L).

Adds the same 5 functions D2L exposes (oauth_authorize_url / refresh_token
/ push_grade / pull_courses / is_scaffold) plus an OAuth state-mint
helper used by the start-OAuth view.

Schoology API specifics (per Schoology Developer Docs):
* OAuth1 + REST API at ``https://api.schoology.com/v1/``
* OAuth2 isn't published; Schoology uses OAuth1 + 3-legged dance
* We expose an OAuth2 *style* authorize URL placeholder for the operator
  UI — the actual flow lands in a follow-up when the integration partner
  test instance is provisioned and the OAuth1 nonce/sig harness is wired.

State mint:
* ``mint_oauth_state(*, tenant_slug, user_pk, redirect_path) -> str``
  Returns a TimestampSigner-signed payload bound to the (tenant, user)
  pair. The state is consumed on callback to defend against CSRF +
  cross-account-binding attacks.
* ``read_oauth_state(raw) -> tuple[dict|None, reason]``
  5-state reason: ok / missing_token / expired_token / bad_token /
  malformed_payload.
"""
from __future__ import annotations

import logging
import urllib.parse as _ulib

logger = logging.getLogger(__name__)

PROVIDER_SLUG = "schoology"
PROVIDER_LABEL = "Schoology"

# Schoology API surface roots (Apr 2026 snapshot).
DEFAULT_API_ROOT = "https://api.schoology.com/v1"
DEFAULT_AUTHORIZE_URL = "https://www.schoology.com/oauth/authorize"
DEFAULT_TOKEN_URL = "https://api.schoology.com/v1/oauth/access_token"

OAUTH_STATE_SALT = "rmc.lms.schoology.oauth_state.v4.00.71"
OAUTH_STATE_TTL_SECONDS = 600  # 10 min


def oauth_authorize_url(
    *,
    client_id: str,
    redirect_uri: str,
    state: str,
    scopes: tuple = (),
    authorize_url: str = DEFAULT_AUTHORIZE_URL,
) -> str:
    """Build the Schoology authorize URL (OAuth2-shaped wrapper around the
    underlying OAuth1 flow; the consent-grant landing page accepts query
    parameters in the OAuth2 shape and bridges internally)."""
    qs = _ulib.urlencode([
        ("response_type", "code"),
        ("client_id", client_id),
        ("redirect_uri", redirect_uri),
        ("state", state),
        ("scope", " ".join(scopes) if scopes else "read write"),
    ])
    sep = "&" if "?" in authorize_url else "?"
    return f"{authorize_url}{sep}{qs}"


def mint_oauth_state(*, tenant_slug: str, user_pk: str | int,
                      redirect_path: str = "/") -> str:
    """Mint a CSRF-safe OAuth state. Payload format:
    ``"<tenant_slug>:<user_pk>:<redirect_path>"``.
    """
    from django.core.signing import TimestampSigner
    signer = TimestampSigner(salt=OAUTH_STATE_SALT)
    safe_redirect = redirect_path if redirect_path.startswith("/") and not redirect_path.startswith("//") else "/"
    payload = f"{tenant_slug}:{user_pk}:{safe_redirect}"
    return signer.sign(payload)


def read_oauth_state(raw: str):
    """Return ``(parsed_dict_or_None, reason)``.

    On success ``parsed_dict_or_None`` is ``{tenant_slug, user_pk, redirect_path}``.
    """
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
    """Honest-stub. Schoology uses OAuth1 long-lived tokens — no refresh
    in the OAuth2 sense. Production wiring lands in v4.00.71+."""
    logger.info("schoology.refresh_token: scaffold call (not wired)")
    return {"ok": False, "reason": "scaffold_not_wired",
            "provider": PROVIDER_SLUG, "wave_landed": "v4.00.71"}


def push_grade(*, base_url: str, access_token: str, course_id: str,
               user_id: str, score: float, max_score: float,
               assignment_id: str = "", grade_id: str = "",
               comment: str = "") -> dict:
    """v4.00.75 — Honest-stub. Real wiring will POST to
    ``/sections/<id>/grades`` per Schoology REST API. This stub returns
    the *intended request shape* under ``would_send`` so calling code can
    unit-test their payload assembly without hitting the network.

    Validates inputs locally so operators get fast feedback on bad data:
      * score / max_score must be numeric and non-negative
      * score must not exceed max_score
      * course_id, user_id must be non-empty
    """
    # Local-only validation — surfaces operator bugs early.
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

    payload_shape = {
        "endpoint": f"{base_url.rstrip('/')}/sections/{course_id}/grades",
        "method": "PUT",
        "body": {
            "grades": {
                "grade": [{
                    "enrollment_id": user_id,
                    "assignment_id": assignment_id,
                    "grade_id": grade_id,
                    "grade": s,
                    "max_points": m,
                    "comment": comment,
                }]
            }
        },
    }
    logger.info("schoology.push_grade: scaffold call (would send %s)", payload_shape["endpoint"])
    return {"ok": False, "reason": "scaffold_not_wired",
            "provider": PROVIDER_SLUG, "course_id": course_id, "user_id": user_id,
            "would_send": payload_shape}


def pull_courses(*, base_url: str, access_token: str) -> list[dict]:
    """Honest-stub. Real wiring walks /users/me/sections/."""
    logger.info("schoology.pull_courses: scaffold call (not wired)")
    return []


def is_scaffold() -> bool:
    # v4.00.83 — Schoology promoted to OAUTH_READY in lms_supported_providers.
    # Kept returning False so callers checking the adapter directly see the
    # current maturity. The honest-stub push_grade above remains for dry-run
    # consumers; live outbound is gated by ``push_grade_live`` + env flag.
    return False


# ---------------------------------------------------------------------------
# v4.00.83 — Live OAuth code-exchange (gated behind env flag).
# v4.00.89 — Audit-hook + refresh-token flow + retry-with-backoff.
# ---------------------------------------------------------------------------
import hashlib as _hashlib
import os
import logging
import time as _time
from typing import Any, Callable

logger = logging.getLogger(__name__)

LIVE_OUTBOUND_ENV = "RMC_SCHOOLOGY_OAUTH_LIVE_OUTBOUND"

# Default OAuth scopes — Schoology splits read/write at the consent screen.
DEFAULT_SCOPES = ("read", "write")

# Schoology refresh-token endpoint. Schoology's OAuth1 long-lived semantics
# do NOT publish a public OAuth2 /refresh endpoint; the partner-test surface
# accepts grant_type=refresh_token on the same token URL. We default to the
# same DEFAULT_TOKEN_URL but expose token_url= as an override so operators
# can point at a different /oauth/refresh path if their tenant has one.
DEFAULT_REFRESH_URL = DEFAULT_TOKEN_URL

# Retry / backoff constants (v4.00.89). Retried statuses are transient
# upstream-layer failures only — 4xx errors stay terminal (caller fault).
# v4.00.90 — 429 added (rate-limit) but only when Retry-After header is
# present + parseable. Without that signal we'd retry blind into the
# same rate-limit ceiling.
_RETRY_HTTP_STATUSES = frozenset({502, 503, 504})
_RETRY_RATE_LIMIT_STATUS = 429
_RETRY_BACKOFF_CAP_SECONDS = 8.0
# Cap Retry-After honoring so a hostile/buggy upstream can't pin us in
# sleep() for hours. 60s aligns with most LMS rate-limit windows.
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
    don't fork audit storage.

    NEVER raises — DB unavailability degrades silently (logged at DEBUG).
    NEVER logs ``client_secret`` / ``access_token`` / ``refresh_token`` /
    ``code`` / ``password`` — caller-supplied ``payload_summary`` is best-
    effort scrubbed in case operator passed a forbidden key by mistake.
    """
    # Best-effort scrub — the four reason-string keys are the canonical
    # secrets we never persist, and we also guard against a caller passing
    # in any ``password``-class identifier.
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
        # Build an actor_hash from tenant_schema so cross-tenant operator
        # ops can be correlated without leaking the schema name verbatim.
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
        logger.debug("schoology._record_audit DB persist failed: %s",
                     type(exc).__name__)
    # Structured INFO log — reason taxonomy surfaced for operator tail -f.
    # NEVER includes any secret-class value (payload_summary already scrubbed).
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
    """v4.00.89 — Call ``call()`` up to ``max_attempts`` times with
    exponential backoff (1s, 2s, 4s, capped at 8s).

    Retries on:
      * ``requests.Timeout`` / ``requests.ConnectionError`` (network)
      * HTTP responses whose ``.status_code`` is in {502, 503, 504}

    Does NOT retry on:
      * 4xx responses (caller fault — re-asking won't help)
      * 2xx responses (success — return immediately)
      * Any non-network exception (programmer error / validation)

    Returns whatever ``call()`` returns on its final attempt, or re-raises
    the last network exception if all attempts exhausted.
    """
    try:
        import requests  # noqa: F401  (only needed for exception types)
        _Timeout = requests.Timeout
        _ConnErr = requests.ConnectionError
    except ImportError:
        # No requests lib -> nothing transient to catch. Single-shot call.
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
        # Inspect status code — retry transient 5xx, return everything else.
        status = getattr(resp, "status_code", None)
        if status in _RETRY_HTTP_STATUSES and attempt + 1 < max_attempts:
            delay = min(base_delay * (2 ** attempt), _RETRY_BACKOFF_CAP_SECONDS)
            _time.sleep(delay)
            continue
        # v4.00.90 — 429 with Retry-After header. Honor the upstream's
        # backoff hint (capped) but bail without retrying if absent.
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
    # Defensive — should be unreachable. raise the last exception we saw.
    if last_exc is not None:
        raise last_exc
    return None


def exchange_authorization_code_for_token(*, code: str, client_id: str,
                                          client_secret: str,
                                          redirect_uri: str,
                                          token_url: str = DEFAULT_TOKEN_URL,
                                          timeout: int = 15,
                                          tenant_schema: str = "") -> dict:
    """Exchange an OAuth authorization code for an access token.

    When LIVE_OUTBOUND_ENV is unset (default), returns a dry-run dict that
    looks like a Schoology success response — useful for testing the
    plumbing without hitting prod.

    On real outbound: returns the upstream JSON OR a structured error dict
    if the upstream returned non-2xx / network error. NEVER raises.

    NEVER logs client_secret / access_token / refresh_token (PII guard).
    """
    # Local validation first — short-circuits w/ validation_error audit.
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
        # Token-class strings NEVER logged here — only exception class.
        logger.warning("schoology token exchange network error: %s",
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
        # v4.00.90 — Decode RFC-6749 § 5.2 error body when present so the
        # operator gets a stable taxonomy (invalid_grant vs invalid_client
        # vs unauthorized_client) instead of just "upstream_error / 400".
        from apps.integrations_marketplace.oauth_live_path_helpers import (
            decode_oauth2_error_response as _decode_err,
        )
        try:
            err_body = resp.json()
        except Exception:  # noqa: BLE001
            err_body = None
        decoded = _decode_err(err_body)
        logger.warning("schoology token exchange http_%s code=%s",
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
    # v4.00.90 — Issue timestamp lets operators wire is_token_expired() on
    # the background refresh sweep. ISO-8601 UTC, no fractional seconds
    # for log-friendliness.
    from datetime import datetime as _dt, timezone as _tz
    body.setdefault("issued_at_iso",
                    _dt.now(_tz.utc).replace(microsecond=0).isoformat())
    # Audit success — token-hash for correlation, NEVER raw token.
    _at_hash = _short_hash(str(body.get("access_token") or ""))
    _rt_hash = _short_hash(str(body.get("refresh_token") or ""))

    # v4.00.91 Wave 24 — H2: redirect_uri post-exchange consistency check.
    # If the upstream echoed a redirect_uri (some do, some don't), validate
    # scheme/host/path against the one we sent. On mismatch we downgrade the
    # result to ok=False with reason="redirect_uri_mismatch" and surface the
    # sub-reason in the audit payload.
    from apps.integrations_marketplace.oauth_live_path_helpers import (
        validate_redirect_uri_consistency as _validate_redirect_uri,
        compare_scopes as _compare_scopes,
        track_refresh_token_issuance as _track_rt_issuance,
    )
    _redir_ok, _redir_reason = _validate_redirect_uri(
        requested_uri=redirect_uri, response_metadata=body,
    )
    # v4.00.91 Wave 24 — H3: scope-mismatch detection (audit-only; never
    # fails the request because granted < requested is sometimes legitimate
    # downscoping per W20 OAuth scope downscoper).
    _scope_cmp = _compare_scopes(
        requested_scopes=DEFAULT_SCOPES,
        granted_scopes=body.get("scope") or "",
    )

    if not _redir_ok:
        # Downgrade the response — operator still gets the token hashes in
        # the audit but the result dict signals the redirect mismatch so
        # calling code refuses to persist the access_token.
        body["ok"] = False
        body["reason"] = "redirect_uri_mismatch"
        body["redirect_uri_mismatch_sub_reason"] = _redir_reason
        body["scope_match"] = _scope_cmp.get("match", True)
        if not _scope_cmp.get("match", True):
            body["scope_missing"] = _scope_cmp.get("missing", [])
            body["scope_extra"] = _scope_cmp.get("extra", [])
        _record_audit(
            action="oauth_exchange", provider=PROVIDER_SLUG,
            ok=False, http_status=status,
            reason="redirect_uri_mismatch",
            tenant_schema=tenant_schema,
            payload_summary={
                "http_status": status,
                "access_token_hash": _at_hash,
                "refresh_token_hash": _rt_hash,
                "expires_in": body.get("expires_in"),
                "redirect_uri_used_hash": _short_hash(redirect_uri),
                "redirect_uri_mismatch_sub_reason": _redir_reason,
                "scope_match": _scope_cmp.get("match", True),
                "scope_missing": _scope_cmp.get("missing", []),
                "scope_extra": _scope_cmp.get("extra", []),
            },
        )
        return body

    body["scope_match"] = _scope_cmp.get("match", True)
    if not _scope_cmp.get("match", True):
        body["scope_missing"] = _scope_cmp.get("missing", [])
        body["scope_extra"] = _scope_cmp.get("extra", [])

    # v4.00.91 Wave 24 — H1: track issuance of the new refresh_token (hash
    # ONLY) in the per-provider ring buffer so future calls can detect
    # rotation + reuse-of-rotated-token attempts.
    if _rt_hash:
        _track_rt_issuance(
            provider=PROVIDER_SLUG,
            tenant_schema=tenant_schema,
            refresh_token_hash=_rt_hash,
            issued_at_iso=body.get("issued_at_iso") or "",
            expires_in_seconds=int(body.get("expires_in") or 0),
        )

    _record_audit(
        action="oauth_exchange", provider=PROVIDER_SLUG,
        ok=True, http_status=status, reason="ok",
        tenant_schema=tenant_schema,
        payload_summary={
            "http_status": status,
            "access_token_hash": _at_hash,
            "refresh_token_hash": _rt_hash,
            "expires_in": body.get("expires_in"),
            "redirect_uri_used_hash": _short_hash(redirect_uri),
            "scope_match": _scope_cmp.get("match", True),
            "scope_missing": _scope_cmp.get("missing", []),
            "scope_extra": _scope_cmp.get("extra", []),
        },
    )
    return body


def refresh_access_token(*, refresh_token: str, client_id: str,
                         client_secret: str,
                         token_url: str = DEFAULT_REFRESH_URL,
                         timeout: int = 15,
                         tenant_schema: str = "") -> dict:
    """v4.00.89 — Refresh an OAuth access token using a refresh-token grant.

    Same env-gate + dry-run pattern as ``exchange_authorization_code_for_token``.

    Schoology technicality: the public Developer API uses OAuth1
    long-lived tokens (no native refresh) but the partner test surface
    accepts ``grant_type=refresh_token`` on the same token URL. Operators
    can override ``token_url=`` if their tenant publishes a dedicated
    ``/oauth/refresh`` endpoint.

    NEVER logs ``client_secret`` / ``refresh_token`` (token_hash only).
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
        logger.warning("schoology token refresh network error: %s",
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
        # v4.00.90 — RFC-6749 § 5.2 error decode mirrors exchange path.
        from apps.integrations_marketplace.oauth_live_path_helpers import (
            decode_oauth2_error_response as _decode_err,
        )
        try:
            err_body = resp.json()
        except Exception:  # noqa: BLE001
            err_body = None
        decoded = _decode_err(err_body)
        logger.warning("schoology token refresh http_%s code=%s",
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

    # v4.00.91 Wave 24 — H1 + H3 wiring on refresh path.
    from apps.integrations_marketplace.oauth_live_path_helpers import (
        compare_scopes as _compare_scopes,
        mark_refresh_token_rotated as _mark_rotated,
        track_refresh_token_issuance as _track_rt_issuance,
    )

    # H1: hash the OLD refresh token (input) for the rotation audit row.
    _old_rt_hash = _short_hash(str(refresh_token or ""))
    _rotated_flag = False
    if _rt_hash and _rt_hash != _old_rt_hash:
        # Upstream issued a NEW refresh token — mark the old hash as
        # rotated so future replay attempts can be flagged.
        _rotated_flag = _mark_rotated(
            provider=PROVIDER_SLUG, refresh_token_hash=_old_rt_hash,
        )
        # Track the NEW refresh token so the NEXT rotation can detect it.
        _track_rt_issuance(
            provider=PROVIDER_SLUG,
            tenant_schema=tenant_schema,
            refresh_token_hash=_rt_hash,
            issued_at_iso=body.get("issued_at_iso") or "",
            expires_in_seconds=int(body.get("expires_in") or 0),
        )
        # Surface the rotation in a DEDICATED audit row so operators can
        # spot the rotation event independently of the broader oauth_refresh
        # row. NEVER includes raw tokens — hashes only.
        _record_audit(
            action="refresh_token_rotation", provider=PROVIDER_SLUG,
            ok=True, http_status=status, reason="ok",
            tenant_schema=tenant_schema,
            payload_summary={
                "old_refresh_token_hash": _old_rt_hash,
                "new_refresh_token_hash": _rt_hash,
                "old_marked_rotated": _rotated_flag,
                "expires_in": body.get("expires_in"),
            },
        )

    # H3: scope compare (audit-only).
    _scope_cmp = _compare_scopes(
        requested_scopes=DEFAULT_SCOPES,
        granted_scopes=body.get("scope") or "",
    )
    body["scope_match"] = _scope_cmp.get("match", True)
    if not _scope_cmp.get("match", True):
        body["scope_missing"] = _scope_cmp.get("missing", [])
        body["scope_extra"] = _scope_cmp.get("extra", [])

    _record_audit(
        action="oauth_refresh", provider=PROVIDER_SLUG,
        ok=True, http_status=status, reason="ok",
        tenant_schema=tenant_schema,
        payload_summary={
            "http_status": status,
            "access_token_hash": _at_hash,
            "refresh_token_hash": _rt_hash,
            "old_refresh_token_hash": _old_rt_hash,
            "old_marked_rotated": _rotated_flag,
            "expires_in": body.get("expires_in"),
            "scope_match": _scope_cmp.get("match", True),
            "scope_missing": _scope_cmp.get("missing", []),
            "scope_extra": _scope_cmp.get("extra", []),
        },
    )
    return body


def push_grade_live(*, access_token: str, section_id: str,
                    assignment_id: str, student_id: str,
                    score: float, max_score: float, comment: str = "",
                    api_base: str = "https://api.schoology.com/v1",
                    timeout: int = 15,
                    tenant_schema: str = "") -> dict:
    """REAL outbound push_grade. Gated behind LIVE_OUTBOUND_ENV. Returns
    upstream JSON on success, structured error dict on failure. NEVER raises."""
    target = f"{api_base}/sections/{section_id}/grades"
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
        "grades": {
            "grade": [{
                "type": 1,
                "assignment_id": assignment_id,
                "enrollment_id": student_id,
                "grade": float(score),
                "max_points": float(max_score),
                "comment": comment[:1000],
            }],
        },
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
                                       "section_id": section_id,
                                       "assignment_id": assignment_id})
        return result

    status = getattr(resp, "status_code", 0)
    if not (200 <= status < 300):
        result = {"ok": False, "dry_run": False, "reason": "upstream_error",
                  "http_status": status}
        _record_audit(action="push_grade_live", provider=PROVIDER_SLUG,
                      ok=False, http_status=status, reason="upstream_error",
                      tenant_schema=tenant_schema,
                      payload_summary={"http_status": status,
                                       "section_id": section_id,
                                       "assignment_id": assignment_id})
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
                                   "section_id": section_id,
                                   "assignment_id": assignment_id,
                                   "student_id_hash": _short_hash(student_id)})
    return result
