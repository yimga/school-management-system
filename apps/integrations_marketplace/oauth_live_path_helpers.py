"""v4.00.90 — OAuth live-path hardening helpers (shared across providers).
v4.00.91 — Wave 24 OAuth security hardening: H1 refresh-token rotation
tracking, H2 redirect_uri post-exchange validation, H3 scope-mismatch
detection. Closes the 3 residual RFC-6749 gaps from the W22 audit.

Three small, well-tested helpers that close the residual gaps in the
v4.00.89 OAuth live path. Shared because both Schoology + D2L (and any
future OAuth2 provider — Canvas, Moodle, Blackboard, PowerSchool) need
the same defenses against real-world upstream behaviors.

1. ``decode_oauth2_error_response(body) -> dict``
   Parses RFC-6749 § 5.2 error response shape::
       {"error": "invalid_grant", "error_description": "...",
        "error_uri": "..."}
   Returns a structured dict w/ taxonomy normalized to a fixed set of
   reasons even when the upstream surfaces a non-spec error code.

2. ``parse_retry_after(header_value) -> float | None``
   Handles RFC-7231 § 7.1.3 Retry-After in both forms:
     * delta-seconds: ``"120"`` -> 120.0
     * HTTP-date: ``"Sun, 30 May 2026 12:00:00 GMT"`` -> seconds-from-now
   Returns ``None`` if the header is missing / malformed.

3. ``is_token_expired(*, issued_at_iso, expires_in_seconds,
   safety_window_seconds=60) -> bool``
   Determines whether a previously-issued OAuth token is expired or
   within the safety window (default 60s = "expiring soon, refresh
   pre-emptively"). Operators wire this into background refresh sweeps
   so the live request path never sees a 401-expired race.

v4.00.91 additions (Wave 24):

4. ``track_refresh_token_issuance(...)`` + ``mark_refresh_token_rotated(...)``
   + ``is_refresh_token_rotated(...)``
   RFC-6749 § 10.4 — single-use refresh-token rotation tracking. Stores
   ONLY SHA-256[:12] hashes per provider in a Lock-protected ring buffer
   (cap 1000 entries per provider, oldest evicted on overflow). Surfaces
   reuse-of-rotated-token attacks to downstream callers w/o ever
   persisting raw token material.

5. ``validate_redirect_uri_consistency(*, requested_uri, response_metadata)``
   Defense-in-depth re-check that the redirect_uri the upstream echoes
   back (when it does — Schoology + Brightspace sometimes do) matches
   the one we sent. Catches scheme / host / path drift that would
   indicate a redirect_uri downgrade attack or upstream misconfig.

6. ``compare_scopes(*, requested_scopes, granted_scopes)``
   RFC-6749 § 3.3 — operator-visible warning when the upstream returns
   a NARROWER (legit downscoping) or BROADER (suspicious — scope creep)
   scope set than we asked for. Does NOT fail the request; the connector
   surfaces ``scope_match`` + ``scope_missing`` / ``scope_extra`` in the
   audit row so operators can spot drift.
"""
from __future__ import annotations

import datetime as _dt
import hashlib as _hashlib
import threading as _threading
import urllib.parse as _urlparse
from collections import deque
from email.utils import parsedate_to_datetime
from typing import Any


# RFC-6749 § 5.2 standard error codes. Anything outside this set folds
# to "upstream_error_unknown" so callers don't have to enumerate vendor
# extensions.
_RFC6749_TOKEN_ERRORS = frozenset({
    "invalid_request",        # missing/malformed param
    "invalid_client",         # bad client_id/client_secret
    "invalid_grant",          # bad code, refresh_token, or redirect_uri
    "unauthorized_client",    # client not allowed this grant type
    "unsupported_grant_type", # server doesn't support requested grant
    "invalid_scope",          # scope outside permitted set
})


def decode_oauth2_error_response(body: Any) -> dict:
    """Normalize a 4xx OAuth2 token-endpoint error body.

    Returns a dict with stable keys:
      * ``error_code``: one of the 6 RFC-6749 codes OR
                        ``"upstream_error_unknown"``
      * ``error_description``: 1-line, max 256 chars, control-char-stripped
      * ``raw_error``: the upstream's verbatim error string (truncated)
      * ``has_error_uri``: bool — whether the upstream provided a docs URL

    Never raises. Body may be a dict, a string, ``None``, anything.
    """
    out = {
        "error_code": "upstream_error_unknown",
        "error_description": "",
        "raw_error": "",
        "has_error_uri": False,
    }
    if not isinstance(body, dict):
        # Some IdPs return text/plain or text/html on errors. We can't
        # parse those structurally — surface the type and bail.
        if body is not None:
            out["raw_error"] = str(body)[:256]
        return out

    raw = str(body.get("error") or "")[:64].strip()
    out["raw_error"] = raw
    code_lc = raw.lower().replace(" ", "_")
    if code_lc in _RFC6749_TOKEN_ERRORS:
        out["error_code"] = code_lc

    desc = body.get("error_description")
    if desc is not None:
        # Strip control chars; cap at 256 to keep audit rows compact.
        clean = "".join(ch for ch in str(desc) if 0x20 <= ord(ch) < 0x7f or ord(ch) > 0xa0)  # magic-number-allow: ascii-codepoint-boundary
        out["error_description"] = clean[:256]

    out["has_error_uri"] = bool(body.get("error_uri"))
    return out


def parse_retry_after(header_value: str | None,
                      *, now: _dt.datetime | None = None) -> float | None:
    """Parse a Retry-After header (RFC 7231 § 7.1.3).

    Two valid forms:
      * delta-seconds: integer string like ``"120"``
      * HTTP-date: like ``"Sun, 30 May 2026 12:00:00 GMT"``

    Returns the number of seconds to wait, or ``None`` if the header is
    missing or unparseable. Never raises. Negative deltas clamped to 0.
    """
    if not header_value:
        return None
    s = str(header_value).strip()
    if not s:
        return None

    # Form 1: delta-seconds (allow decimal too, even though spec says int).
    try:
        delta = float(s)
        return max(0.0, delta)
    except (ValueError, TypeError):
        pass

    # Form 2: HTTP-date.
    try:
        target = parsedate_to_datetime(s)
    except (TypeError, ValueError):
        return None
    if target is None:
        return None
    if now is None:
        now = _dt.datetime.now(_dt.timezone.utc)
    # parsedate_to_datetime returns timezone-aware when the input
    # carries a GMT/timezone suffix; otherwise naive (assume UTC).
    if target.tzinfo is None:
        target = target.replace(tzinfo=_dt.timezone.utc)
    delta = (target - now).total_seconds()
    return max(0.0, delta)


def is_token_expired(*, issued_at_iso: str,
                     expires_in_seconds: int,
                     safety_window_seconds: int = 60,
                     now: _dt.datetime | None = None) -> bool:
    """Has the OAuth access token issued at ``issued_at_iso`` expired
    (or will expire within ``safety_window_seconds``)?

    Wire this into background-refresh sweeps so the live request path
    never sees a 401 because a token raced across its expiry boundary.

    Returns True ("treat as expired") if:
      * ``issued_at_iso`` is missing / unparseable (safer to refresh)
      * ``expires_in_seconds`` is missing or <= 0
      * ``now - issued_at >= (expires_in - safety_window)``

    Returns False otherwise (token is valid, no refresh needed yet).
    """
    if not issued_at_iso or not isinstance(expires_in_seconds, (int, float)):
        return True
    if expires_in_seconds <= 0:
        return True
    try:
        # Accept both "...Z" and "...+00:00" forms.
        clean = str(issued_at_iso).strip()
        if clean.endswith("Z"):
            clean = clean[:-1] + "+00:00"
        issued = _dt.datetime.fromisoformat(clean)
    except (ValueError, TypeError):
        return True
    if issued.tzinfo is None:
        issued = issued.replace(tzinfo=_dt.timezone.utc)
    if now is None:
        now = _dt.datetime.now(_dt.timezone.utc)
    elapsed = (now - issued).total_seconds()
    return elapsed >= max(0, int(expires_in_seconds) - max(0, int(safety_window_seconds)))


# ---------------------------------------------------------------------------
# v4.00.91 Wave 24 — H1: Refresh-token rotation tracking (RFC-6749 § 10.4)
# ---------------------------------------------------------------------------
# Lock-protected per-provider ring buffer. Cap 1000 entries; on overflow the
# oldest entry evicts. We store ONLY SHA-256[:12] hashes — raw token bytes
# never enter this module's memory beyond the in-helper hash() call site.
#
# Why a ring buffer instead of a DB table:
#   * The OAuth retry path needs O(1) "have I seen this token-hash get
#     rotated?" lookups — a DB round-trip would dominate the path.
#   * Refresh tokens are short-lived enough (most upstreams: minutes to
#     hours; Schoology long-lived but still bounded) that 1000 hashes per
#     provider covers a deep enough window for forensic correlation.
#   * The W19 LMSDiagActionAudit DB row carries the same hashes for the
#     long-term forensic trail — this in-process buffer is just for the
#     hot retry path.
_REFRESH_TOKEN_RING_CAP: int = 1000

_refresh_token_lock: _threading.Lock = _threading.Lock()
# provider_slug -> deque[dict]: each entry shape:
#   {"hash": "abc123def456", "issued_at_iso": "...",
#    "expires_in_seconds": 3600, "tenant_schema": "school_xyz",
#    "rotated": False}
_refresh_token_rings: dict[str, "deque[dict[str, Any]]"] = {}


def _short_hash_for_tracking(value: str) -> str:
    """SHA-256[:12] of a string — used to correlate refresh tokens in the
    ring buffer WITHOUT keeping the raw token in memory. Empty input -> ""."""
    if not value:
        return ""
    return _hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]


def _get_or_create_ring(provider: str) -> "deque[dict[str, Any]]":
    """Lazy-init the per-provider deque inside the lock. Caller MUST hold
    ``_refresh_token_lock`` before calling."""
    ring = _refresh_token_rings.get(provider)
    if ring is None:
        ring = deque(maxlen=_REFRESH_TOKEN_RING_CAP)
        _refresh_token_rings[provider] = ring
    return ring


def track_refresh_token_issuance(*, provider: str, tenant_schema: str,
                                 refresh_token_hash: str,
                                 issued_at_iso: str,
                                 expires_in_seconds: int) -> None:
    """Record a freshly-issued refresh-token (by HASH ONLY) in the per-provider
    ring buffer. Thread-safe.

    ``refresh_token_hash`` MUST be the caller-computed SHA-256[:12] — this
    function does NOT accept raw tokens, defensively guaranteeing the raw
    bytes never reach this module.

    No-ops on empty hash (caller already handles the case where the upstream
    didn't return a refresh_token at all).

    NEVER raises — internal errors degrade silently (logged via the calling
    connector's standard logger; helpers stay print-free per project rules).
    """
    if not refresh_token_hash:
        return
    if not provider:
        return
    entry: dict[str, Any] = {
        "hash": str(refresh_token_hash)[:32],
        "issued_at_iso": str(issued_at_iso or "")[:32],
        "expires_in_seconds": int(expires_in_seconds or 0),
        "tenant_schema_hash": _short_hash_for_tracking(str(tenant_schema or "")),
        "rotated": False,
    }
    with _refresh_token_lock:
        ring = _get_or_create_ring(str(provider))
        ring.append(entry)


def mark_refresh_token_rotated(*, provider: str,
                               refresh_token_hash: str) -> bool:
    """Flag a refresh-token hash as rotated (i.e. the upstream issued a NEW
    refresh token in response to using this one, so this one must never be
    replayed).

    If the hash already lives in the ring buffer, the existing entry is
    marked. If not (e.g. process restarted since the token was issued, or
    the entry aged out of the ring's 1000-entry cap), a NEW
    ``rotated=True`` entry is inserted so future replay checks can flag it.
    This auto-insert semantics is critical: refresh-token rotation is the
    primary defense against stolen-token replay, and an empty ring buffer
    on cold start MUST NOT silently neutralize the defense.

    Returns True if the hash was already known + just got marked; False if
    the hash was inserted fresh as already-rotated. Calling code uses the
    return value only for audit-row correlation, never to gate the request.
    """
    if not refresh_token_hash or not provider:
        return False
    target = str(refresh_token_hash)[:32]
    with _refresh_token_lock:
        ring = _get_or_create_ring(str(provider))
        for entry in ring:
            if entry.get("hash") == target:
                entry["rotated"] = True
                return True
        # Not found in ring -> insert a fresh entry with rotated=True so
        # the rotation defense survives process restarts + ring-evictions.
        ring.append({
            "hash": target,
            "issued_at_iso": "",
            "expires_in_seconds": 0,
            "tenant_schema_hash": "",
            "rotated": True,
        })
    return False


def is_refresh_token_rotated(*, provider: str,
                             refresh_token_hash: str) -> bool:
    """Has the refresh-token (identified by its SHA-256[:12]) already been
    rotated? Downstream callers check this BEFORE retrying with a stored
    refresh token to detect the "stolen-and-replayed" scenario.

    Returns True only if we have positive evidence of rotation. Unknown
    tokens (never seen + cap-evicted from the ring) return False — the
    caller treats unknowns as "not provably rotated" and falls back to
    other defenses (upstream's own invalid_grant response).
    """
    if not refresh_token_hash or not provider:
        return False
    target = str(refresh_token_hash)[:32]
    with _refresh_token_lock:
        ring = _refresh_token_rings.get(str(provider))
        if ring is None:
            return False
        for entry in ring:
            if entry.get("hash") == target:
                return bool(entry.get("rotated"))
    return False


def _refresh_token_ring_snapshot(provider: str) -> list[dict[str, Any]]:
    """Test-only inspection helper. Returns a defensive copy of the ring's
    entries (in insertion order, oldest first). Used by the smoke harness;
    operator code should rely on the public ``is_refresh_token_rotated``
    helper rather than peering into ring internals."""
    with _refresh_token_lock:
        ring = _refresh_token_rings.get(str(provider))
        if ring is None:
            return []
        return [dict(e) for e in ring]


def _reset_refresh_token_rings_for_tests() -> None:
    """Test-only — clear all per-provider rings. The smoke harness calls this
    between test groups to keep cases independent."""
    with _refresh_token_lock:
        _refresh_token_rings.clear()


# ---------------------------------------------------------------------------
# v4.00.91 Wave 24 — H2: redirect_uri post-exchange validation
# ---------------------------------------------------------------------------
def validate_redirect_uri_consistency(*, requested_uri: str,
                                      response_metadata: dict | None
                                      ) -> tuple[bool, str]:
    """Detect after-the-fact drift between the redirect_uri we SENT to the
    upstream and any redirect_uri it (or its echo / metadata) reports back.

    Returns a 2-tuple ``(ok: bool, reason: str)`` with reason taxonomy:

      * ``"ok"`` — either no inconsistency detected OR the response carries
        no redirect_uri hint at all (the common case; not all upstreams
        echo the value back).
      * ``"scheme_mismatch"`` — http vs https or anything else (defends
        against TLS-downgrade exfil).
      * ``"host_mismatch"`` — a different host slipped through (defends
        against open-redirect chained with stolen code).
      * ``"path_mismatch"`` — path component drifted (catches typos +
        deliberate misconfig).
      * ``"invalid_requested_uri"`` — caller passed a non-URL string.

    Never raises. The caller turns ``ok=False`` into a downgrade of the
    exchange result (``reason="redirect_uri_mismatch"``) and surfaces the
    sub-reason in the audit payload.

    The response_metadata dict is treated as best-effort: we accept either
    ``response_metadata["redirect_uri"]`` (per-spec echo) or
    ``response_metadata["redirect_url"]`` (common vendor extension) or
    ``response_metadata["request"]["redirect_uri"]`` (nested form).
    """
    if not requested_uri:
        return False, "invalid_requested_uri"
    try:
        req_parsed = _urlparse.urlsplit(str(requested_uri))
    except (ValueError, TypeError):
        return False, "invalid_requested_uri"
    if not req_parsed.scheme or not req_parsed.netloc:
        return False, "invalid_requested_uri"

    # No metadata to compare against -> we cannot detect drift, treat as ok.
    if not isinstance(response_metadata, dict) or not response_metadata:
        return True, "ok"

    echoed = ""
    if isinstance(response_metadata.get("redirect_uri"), str):
        echoed = response_metadata["redirect_uri"]
    elif isinstance(response_metadata.get("redirect_url"), str):
        echoed = response_metadata["redirect_url"]
    elif isinstance(response_metadata.get("request"), dict):
        nested = response_metadata["request"].get("redirect_uri")
        if isinstance(nested, str):
            echoed = nested
    if not echoed:
        return True, "ok"

    try:
        resp_parsed = _urlparse.urlsplit(echoed)
    except (ValueError, TypeError):
        # Echo malformed -> conservatively treat as inconsistent.
        return False, "path_mismatch"

    # Scheme + host comparisons are case-insensitive per RFC 3986 § 3.1/3.2.2.
    if req_parsed.scheme.lower() != resp_parsed.scheme.lower():
        return False, "scheme_mismatch"
    if req_parsed.netloc.lower() != resp_parsed.netloc.lower():
        return False, "host_mismatch"
    # Path comparison is case-sensitive per RFC 3986 § 3.3.
    if req_parsed.path != resp_parsed.path:
        return False, "path_mismatch"
    return True, "ok"


# ---------------------------------------------------------------------------
# v4.00.91 Wave 24 — H3: Scope-mismatch detection (RFC-6749 § 3.3)
# ---------------------------------------------------------------------------
def _normalize_scope_set(scopes: Any) -> set[str]:
    """Accept either a sequence-of-strings OR a space-delimited string (the
    on-the-wire form) and return a normalized set of non-empty tokens."""
    if not scopes:
        return set()
    if isinstance(scopes, str):
        return {tok for tok in scopes.split() if tok}
    if isinstance(scopes, (list, tuple, set, frozenset)):
        out: set[str] = set()
        for item in scopes:
            if isinstance(item, str) and item.strip():
                out.add(item.strip())
        return out
    return set()


def compare_scopes(*, requested_scopes: Any,
                   granted_scopes: Any) -> dict[str, Any]:
    """Compare a requested vs granted OAuth scope set.

    Returns a structured dict:

      * If ``granted ⊇ requested`` (the upstream gave us at least everything
        we asked for): ``{"match": True}``.
      * Otherwise: ``{"match": False, "missing": [...], "extra": [...]}``
        where ``missing`` is sorted ``requested - granted`` (the operator-
        visible "narrower" case — legitimate downscoping per W20 OAuth scope
        downscoper, but worth surfacing) and ``extra`` is sorted
        ``granted - requested`` (the suspicious "broader" case — scope creep).

    Both inputs may be a sequence-of-strings OR a space-delimited string.
    Never raises.
    """
    req = _normalize_scope_set(requested_scopes)
    granted = _normalize_scope_set(granted_scopes)
    missing = sorted(req - granted)
    extra = sorted(granted - req)
    if not missing and not extra:
        return {"match": True}
    # If granted ⊇ requested, missing is empty — but extra may still be
    # non-empty (broader). Treat any non-equal-set as match=False so the
    # operator gets both signals (downscoping + scope-creep) in one audit row.
    return {"match": False, "missing": missing, "extra": extra}
