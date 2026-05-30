"""v4.00.90 — OAuth live-path hardening helpers (shared across providers).

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
"""
from __future__ import annotations

import datetime as _dt
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
        clean = "".join(ch for ch in str(desc) if 0x20 <= ord(ch) < 0x7f or ord(ch) > 0xa0)
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
