"""Wave L-followup: cache-backed CSP violation counter reader.

Pair to ``apps/security/csp_report_view.py`` — the report endpoint
writes per-hour buckets; this module reads them for the readiness
preflight and any future operator dashboards.

Counter shape (cache-backed; survives only as long as the cache
backend's TTL):

    csp_violations:bucket:<hour_epoch>             -> int total this hour
    csp_violations:directive:<hour_epoch>:<dir>    -> int per-directive

Reading is best-effort: cache misses (TTL expired, cache flushed,
backend offline) return 0 rather than raising. Counters are runtime
telemetry, not an audit log.
"""

from __future__ import annotations

import time

from django.core.cache import cache

_COUNTER_KEY_TOTAL = "csp_violations:bucket:{hour}"
_COUNTER_KEY_DIRECTIVE = "csp_violations:directive:{hour}:{directive}"

# Directives the preflight cares about specifically. Other directives
# fold into the total but aren't broken out per-line.
TRACKED_DIRECTIVES: tuple[str, ...] = (
    "script-src",
    "style-src",
    "img-src",
    "connect-src",
    "frame-ancestors",
    "object-src",
    "base-uri",
    "form-action",
    "default-src",
)


def _current_hour_bucket() -> int:
    return int(time.time() // 3600)


def _read(key: str) -> int:
    try:
        value = cache.get(key, 0)
    except Exception:  # noqa: BLE001 — telemetry read must never raise
        return 0
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def violations_in_last_hours(hours: int = 24) -> int:
    """Return total CSP violations across the last N hours.

    Returns 0 when the cache backend is unreachable or no violations
    have been recorded — callers must treat 0 as "unknown / no data",
    not "definitely zero".
    """
    if hours <= 0:
        return 0
    now_bucket = _current_hour_bucket()
    total = 0
    for offset in range(hours):
        key = _COUNTER_KEY_TOTAL.format(hour=now_bucket - offset)
        total += _read(key)
    return total


def violations_by_directive_in_last_hours(
    hours: int = 24,
) -> dict[str, int]:
    """Return {directive: count} aggregated across the last N hours.

    Only TRACKED_DIRECTIVES are surfaced; others (and the "_unknown"
    bucket the writer falls back to) are omitted from the per-directive
    view. The bucket total from ``violations_in_last_hours`` is the
    authoritative grand total.
    """
    if hours <= 0:
        return {}
    now_bucket = _current_hour_bucket()
    out: dict[str, int] = {d: 0 for d in TRACKED_DIRECTIVES}
    for offset in range(hours):
        for directive in TRACKED_DIRECTIVES:
            key = _COUNTER_KEY_DIRECTIVE.format(
                hour=now_bucket - offset, directive=directive
            )
            out[directive] += _read(key)
    # Strip zero entries so the caller's output stays tight.
    return {d: c for d, c in out.items() if c > 0}


__all__ = [
    "TRACKED_DIRECTIVES",
    "violations_by_directive_in_last_hours",
    "violations_in_last_hours",
]
