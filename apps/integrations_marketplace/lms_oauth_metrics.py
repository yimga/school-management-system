"""v4.00.77 — OAuth refresh metrics module.

Process-singleton counters that increment on every OAuth refresh attempt
across the LMS connector beat sweeps. Operators read these via the
diagnostics dashboard to spot provider-level drift (e.g. Canvas refresh
success rate dropping over time).

These counters are intentionally simple - mirror the
``_RETENTION_SWEEP_COUNTERS`` pattern in
``apps.migration_cloud.views_lms_diagnostics``. Persistent rollup lives
in ``LMSDiagActionAudit``; this module is the fast hot-cache.

Exposed:
  * ``record_refresh_attempt(provider, ok, reason="")``
  * ``get_oauth_metrics_snapshot()`` → ``{provider: {attempts, ok, failed,
      ok_rate_pct, last_reason}}``
  * ``reset_oauth_metrics()`` — test-only.
"""
from __future__ import annotations

import logging
from threading import Lock

logger = logging.getLogger(__name__)

_OAUTH_METRICS: dict[str, dict] = {}
_LOCK = Lock()


def record_refresh_attempt(provider: str, ok: bool, reason: str = "") -> None:
    """Bump the counters for ``provider``. NEVER raises."""
    try:
        with _LOCK:
            bucket = _OAUTH_METRICS.setdefault(provider or "unknown", {
                "attempts": 0, "ok": 0, "failed": 0,
                "last_reason": "", "last_ok": True,
            })
            bucket["attempts"] += 1
            if ok:
                bucket["ok"] += 1
                bucket["last_ok"] = True
            else:
                bucket["failed"] += 1
                bucket["last_ok"] = False
            if reason:
                bucket["last_reason"] = reason[:120]
    except Exception as exc:  # noqa: BLE001
        logger.debug("oauth metrics record failed: %s", exc)


def get_oauth_metrics_snapshot() -> dict[str, dict]:
    """Return a defensive copy of the metrics keyed by provider."""
    out: dict[str, dict] = {}
    with _LOCK:
        for provider, bucket in _OAUTH_METRICS.items():
            attempts = bucket["attempts"]
            ok_rate = round(100.0 * bucket["ok"] / attempts, 2) if attempts else 0.0
            out[provider] = {
                "attempts": attempts,
                "ok": bucket["ok"],
                "failed": bucket["failed"],
                "ok_rate_pct": ok_rate,
                "last_reason": bucket["last_reason"],
                "last_ok": bucket["last_ok"],
            }
    return out


def reset_oauth_metrics() -> None:
    """Test-only helper. tenant-isolation-allow: process-singleton-metrics-reset."""
    with _LOCK:
        _OAUTH_METRICS.clear()
