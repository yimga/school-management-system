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


# v4.00.82 — Prometheus text-exposition export.
#
# Returns the OpenMetrics 0.0.4 text format documented at
# https://prometheus.io/docs/instrumenting/exposition_formats/.
# Metric names follow ``rmc_lms_oauth_refresh_*`` convention so they
# coexist cleanly with the platform's other Prometheus surface
# (apps.observability.metrics, v3.39.0).
#
# WIRING DECISION: ``apps.observability.views_metrics.PrometheusMetricsView``
# already serves ``/metrics/`` via ``prometheus_client.generate_latest()``
# against the default ``prometheus_client`` registry. Cross-registry
# mixing (registering our singletons into that registry from a separate
# module) is fragile across process restarts / test isolation, so v4.00.82
# parks our LMS OAuth metrics on a PARALLEL endpoint
# (``/lms-oauth-metrics/``, URL name ``metrics-lms-oauth-text``) per the
# Wave 14 docket's "safer path" guidance. The existing scrape view is
# untouched. Operators add a second Prometheus scrape job pointing at the
# new endpoint.
#
# Snapshot shape note: v4.00.77's ``get_oauth_metrics_snapshot()`` uses
# the keys ``attempts`` / ``ok`` / ``failed`` (NOT ``successes`` /
# ``failures``). The Prometheus metric NAMES still follow the
# canonical ``_successes_total`` / ``_failures_total`` convention so
# downstream dashboards read naturally — only the dict-key extraction
# is mapped.
_PROM_NAMESPACE = "rmc_lms_oauth"


def render_prometheus_metrics() -> str:
    """Return the LMS OAuth metrics in Prometheus text-exposition format.

    Never raises — returns a comment-only string on failure so the
    /metrics/ endpoint can serve it without a 500.
    """
    try:
        snap = get_oauth_metrics_snapshot()
    except Exception as exc:  # noqa: BLE001
        logger.debug("oauth metrics snapshot for prom export failed: %s", exc)
        return (
            "# HELP rmc_lms_oauth_snapshot_error 1 = snapshot failed\n"
            "# TYPE rmc_lms_oauth_snapshot_error gauge\n"
            "rmc_lms_oauth_snapshot_error 1\n"
        )

    lines: list[str] = []
    # Attempts counter (cumulative since process start / last reset).
    lines.append(
        "# HELP rmc_lms_oauth_refresh_attempts_total OAuth refresh attempts by provider."
    )
    lines.append("# TYPE rmc_lms_oauth_refresh_attempts_total counter")
    for provider, row in sorted(snap.items()):
        attempts = int(row.get("attempts", 0))
        lines.append(
            f'rmc_lms_oauth_refresh_attempts_total{{provider="{_escape_label(provider)}"}} {attempts}'
        )

    # Successes — v4.00.77 snapshot exposes this as the "ok" key.
    lines.append(
        "# HELP rmc_lms_oauth_refresh_successes_total OAuth refresh successes by provider."
    )
    lines.append("# TYPE rmc_lms_oauth_refresh_successes_total counter")
    for provider, row in sorted(snap.items()):
        successes = int(row.get("ok", row.get("successes", 0)))
        lines.append(
            f'rmc_lms_oauth_refresh_successes_total{{provider="{_escape_label(provider)}"}} {successes}'
        )

    # Failures — v4.00.77 snapshot exposes this as the "failed" key.
    lines.append(
        "# HELP rmc_lms_oauth_refresh_failures_total OAuth refresh failures by provider."
    )
    lines.append("# TYPE rmc_lms_oauth_refresh_failures_total counter")
    for provider, row in sorted(snap.items()):
        failures = int(row.get("failed", row.get("failures", 0)))
        lines.append(
            f'rmc_lms_oauth_refresh_failures_total{{provider="{_escape_label(provider)}"}} {failures}'
        )

    # v4.00.84 — Per-tenant breakdown. Snapshot the dict under the lock
    # first so iteration doesn't trip if a new tenant is added mid-render.
    try:
        with _LOCK:
            per_tenant_snap = {
                (p, t): dict(v) for (p, t), v in _OAUTH_METRICS_PER_TENANT.items()
            }
    except Exception as exc:  # noqa: BLE001
        logger.debug("oauth per-tenant snapshot for prom export failed: %s", exc)
        per_tenant_snap = {}

    if per_tenant_snap:
        lines.append(
            "# HELP rmc_lms_oauth_refresh_attempts_by_tenant_total OAuth refresh attempts by (provider, tenant)."
        )
        lines.append("# TYPE rmc_lms_oauth_refresh_attempts_by_tenant_total counter")
        for (provider, tenant), row in sorted(per_tenant_snap.items()):
            attempts = int(row.get("attempts", 0))
            lines.append(
                f'rmc_lms_oauth_refresh_attempts_by_tenant_total{{provider="{_escape_label(provider)}",tenant="{_escape_label(tenant)}"}} {attempts}'
            )

        lines.append(
            "# HELP rmc_lms_oauth_refresh_successes_by_tenant_total OAuth refresh successes by (provider, tenant)."
        )
        lines.append("# TYPE rmc_lms_oauth_refresh_successes_by_tenant_total counter")
        for (provider, tenant), row in sorted(per_tenant_snap.items()):
            successes = int(row.get("ok", 0))
            lines.append(
                f'rmc_lms_oauth_refresh_successes_by_tenant_total{{provider="{_escape_label(provider)}",tenant="{_escape_label(tenant)}"}} {successes}'
            )

        lines.append(
            "# HELP rmc_lms_oauth_refresh_failures_by_tenant_total OAuth refresh failures by (provider, tenant)."
        )
        lines.append("# TYPE rmc_lms_oauth_refresh_failures_by_tenant_total counter")
        for (provider, tenant), row in sorted(per_tenant_snap.items()):
            failures = int(row.get("failed", 0))
            lines.append(
                f'rmc_lms_oauth_refresh_failures_by_tenant_total{{provider="{_escape_label(provider)}",tenant="{_escape_label(tenant)}"}} {failures}'
            )

    return "\n".join(lines) + "\n"


def _escape_label(value: str) -> str:
    """Escape a Prometheus label value per text-exposition spec
    (backslash, double-quote, newline)."""
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


# v4.00.84 — Per-tenant metric breakdown (optional dimension).
#
# Wave 16 Target 3 adds a parallel per-(provider, tenant_schema) tracking
# dict that lets multi-tenant operators see OAuth refresh metrics broken
# down per tenant. The existing global surface
# (record_refresh_attempt / get_oauth_metrics_snapshot / reset_oauth_metrics)
# is UNCHANGED — callers that don't care about the tenant dimension see
# zero behavior drift. Per-tenant tracking is opt-in via the dedicated
# record_refresh_attempt_for_tenant() entry point, which ALSO updates
# the global aggregates so the v4.00.77 snapshot keeps reflecting total
# attempts across all tenants.

# Per-tenant nested: dict[(provider, tenant_schema)] -> dict (same shape as global)
_OAUTH_METRICS_PER_TENANT: dict[tuple[str, str], dict] = {}


def record_refresh_attempt_for_tenant(*, provider: str, tenant_schema: str, ok: bool, reason: str = "") -> None:
    """Like record_refresh_attempt but ALSO tracks per-tenant.

    The global per-provider stats are still updated (so existing callers
    that read get_oauth_metrics_snapshot keep seeing aggregated counts).
    Per-tenant detail is recorded in a parallel dict accessible via
    get_oauth_metrics_per_tenant_snapshot().
    """
    # First, update the global (existing behavior, never breaks)
    try:
        record_refresh_attempt(provider, ok, reason=reason)
    except Exception as exc:  # noqa: BLE001
        logger.debug("global record_refresh_attempt failed: %s", exc)
    # Then per-tenant tracking
    with _LOCK:  # use the same lock as the global mutation
        try:
            from django.utils import timezone as _tz
            now_iso = _tz.now().isoformat()
        except Exception:  # noqa: BLE001
            from datetime import datetime, timezone as _dtz
            now_iso = datetime.now(_dtz.utc).isoformat()

        key = (str(provider)[:64], str(tenant_schema or "")[:64])
        row = _OAUTH_METRICS_PER_TENANT.setdefault(key, {
            "attempts": 0, "ok": 0, "failed": 0,
            "last_attempt_at": "", "last_failure_reason": "",
        })
        row["attempts"] += 1
        row["last_attempt_at"] = now_iso
        if ok:
            row["ok"] += 1
        else:
            row["failed"] += 1
            if reason:
                row["last_failure_reason"] = str(reason)[:120]


def get_oauth_metrics_per_tenant_snapshot() -> dict:
    """Return a copy of the per-tenant metrics snapshot.

    Returns ``{f"{provider}|{tenant}": {attempts, ok, failed, ...}}``
    keyed by ``"<provider>|<tenant_schema>"`` for ease of serialization.
    Caller mutating the returned dict does not affect the live counters.
    """
    with _LOCK:
        return {
            f"{p}|{t}": dict(v) for (p, t), v in _OAUTH_METRICS_PER_TENANT.items()
        }


def reset_oauth_metrics_per_tenant() -> None:
    """Test-only helper. tenant-isolation-allow: process-singleton-metrics-reset."""
    with _LOCK:
        _OAUTH_METRICS_PER_TENANT.clear()
