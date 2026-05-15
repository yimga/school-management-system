"""CSP violation report endpoint.

Browsers POST a CSP violation report (per the Report-Only header's
``report-uri``) when a directive fires. This view ingests + logs each report
so operators can shrink the policy over time.

The endpoint is intentionally:

- CSRF-exempt (browsers don't send our CSRF cookie on a CSP report POST)
- Rate-limited (a single tab refresh can generate many reports)
- Body-size-capped (drop reports > 64 KiB to avoid log spam)
- PII-free in the log line (only directive + blocked-uri + document-uri)

Wave L-followup (2026-05-15): in addition to logging, the endpoint
maintains a **cache-backed per-directive hourly counter**. This is
ephemeral runtime telemetry — survives only as long as the cache
backend's TTL — but it's enough to let
``apps.security.csp_readiness.assess_csp_readiness`` surface "X
violations in the last hour" without introducing a persistence model.
For long-term retention, log aggregation (Sentry / ELK) remains the
canonical surface.
"""

from __future__ import annotations

import json
import logging
import time

from django.core.cache import cache
from django.http import HttpResponse, HttpResponseBadRequest
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from apps.security.rate_limit import rate_limit


logger = logging.getLogger(__name__)


_MAX_BODY_BYTES = 64 * 1024

# Cache-backed counter (Wave L-followup). Key shape:
#   csp_violations:bucket:<hour_epoch>             — int total this hour
#   csp_violations:directive:<hour_epoch>:<dir>    — int per-directive this hour
# Each key TTLs out 25 hours after creation so the preflight can read
# the last 24 windows without manual eviction.
_COUNTER_TTL_SECONDS = 25 * 3600
_COUNTER_KEY_TOTAL = "csp_violations:bucket:{hour}"
_COUNTER_KEY_DIRECTIVE = "csp_violations:directive:{hour}:{directive}"


def _current_hour_bucket() -> int:
    """Return the integer epoch-hour for the current wall clock."""
    return int(time.time() // 3600)


def _safe_increment(key: str) -> None:
    """Increment a cache key with race-tolerant fallback to add-then-incr.

    Django's cache `incr` raises ValueError if the key doesn't exist; the
    canonical race-tolerant pattern is `add` first (no-op if present),
    then `incr`. Both can fail under cache backend errors — we swallow
    those silently because counter loss is preferable to dropping a
    CSP violation report.
    """
    try:
        cache.add(key, 0, _COUNTER_TTL_SECONDS)
        cache.incr(key)
    except (ValueError, Exception):  # noqa: BLE001 — telemetry must never block
        pass


@csrf_exempt
@require_POST
@rate_limit(scope="csp_report", limit=200, window_seconds=60)
def csp_violation_report(request):
    """Receive a CSP violation report. Always returns 204 No Content on success."""
    body = (request.body or b"")[:_MAX_BODY_BYTES]
    try:
        payload = json.loads(body.decode("utf-8", errors="replace") or "{}")
    except (json.JSONDecodeError, ValueError):
        return HttpResponseBadRequest("invalid JSON")

    # Browsers wrap the report under "csp-report" (legacy) or send it directly
    # for Reporting API. Normalise both.
    report = payload.get("csp-report") if isinstance(payload, dict) else None
    if not isinstance(report, dict):
        report = payload if isinstance(payload, dict) else {}

    directive = str(report.get("violated-directive") or report.get("effective-directive") or "")[:120]
    blocked = str(report.get("blocked-uri") or "")[:200]
    doc_uri = str(report.get("document-uri") or "")[:200]
    src_file = str(report.get("source-file") or "")[:200]
    line_no = report.get("line-number") or 0

    logger.warning(
        "csp_violation directive=%s blocked=%s doc=%s src=%s line=%s",
        directive,
        blocked,
        doc_uri,
        src_file,
        line_no,
    )

    # Wave L-followup: cache-backed counter for the readiness preflight.
    # Normalise the directive to its first word (e.g. "script-src" out of
    # "script-src 'nonce-...'") so the per-directive bucket aggregates
    # cleanly. Empty directives bucket as "_unknown" so they're still
    # visible.
    bucket = _current_hour_bucket()
    short_directive = (directive.split(" ", 1)[0] if directive else "_unknown")[:32]
    _safe_increment(_COUNTER_KEY_TOTAL.format(hour=bucket))
    _safe_increment(
        _COUNTER_KEY_DIRECTIVE.format(hour=bucket, directive=short_directive)
    )

    return HttpResponse(status=204)
