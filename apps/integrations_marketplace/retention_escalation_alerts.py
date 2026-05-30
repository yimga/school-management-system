"""v4.00.87 — Retention escalation alert emission.

When the retention sweep is about to delete a large batch (threshold
configurable, default 1000) OR when a per-tenant override sits below
a regulatory floor (default 3 years for FERPA), emit an alert event.

In-process ring buffer (cap 200) of recent alerts. Operator subscribes
via list_recent_retention_alerts() or a future dashboard endpoint.

NEVER alerts contain raw row data — only counts, tenant_schema, table
name, severity.
"""
from __future__ import annotations
import logging
import threading
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


LARGE_BATCH_THRESHOLD_DEFAULT = 1000
REGULATORY_FLOOR_YEARS_DEFAULT = 3  # FERPA-ish baseline

_ALERTS_RING: list[dict] = []
_ALERTS_RING_CAP = 200
_ALERTS_LOCK = threading.Lock()


def emit_retention_alert(*, severity: str, alert_type: str, tenant_schema: str, target_table: str, count: int = 0, reason: str = "", retention_years: int | None = None) -> dict:
    """Emit a retention alert. Severity: info / warning / critical.
    NEVER raises. Returns the alert dict."""
    now_iso = datetime.now(timezone.utc).isoformat()
    alert = {
        "iso_at": now_iso,
        "severity": severity[:16],
        "alert_type": alert_type[:64],
        "tenant_schema": (tenant_schema or "")[:64],
        "target_table": (target_table or "")[:64],
        "count": int(count),
        "reason": (reason or "")[:256],
        "retention_years": retention_years if retention_years is not None else None,
    }
    try:
        with _ALERTS_LOCK:
            if len(_ALERTS_RING) >= _ALERTS_RING_CAP:
                _ALERTS_RING.pop(0)  # evict oldest
            _ALERTS_RING.append(alert)
        logger.info("retention_alert sev=%s type=%s tenant=%s table=%s count=%s",
                    alert["severity"], alert["alert_type"], alert["tenant_schema"],
                    alert["target_table"], alert["count"])
    except Exception as exc:  # noqa: BLE001
        logger.debug("emit_retention_alert ring write failed: %s", exc)
    return alert


def check_large_batch_threshold(*, tenant_schema: str, target_table: str, count: int, threshold: int = LARGE_BATCH_THRESHOLD_DEFAULT) -> dict | None:
    """If count >= threshold, emit a warning alert + return it. Else None."""
    if count < threshold:
        return None
    severity = "critical" if count >= threshold * 10 else "warning"
    return emit_retention_alert(
        severity=severity, alert_type="large_batch_pending_purge",
        tenant_schema=tenant_schema, target_table=target_table,
        count=count,
        reason=f"about_to_delete_{count}_rows_threshold_{threshold}",
    )


def check_override_below_floor(*, tenant_schema: str, target_table: str, retention_years: int, floor: int = REGULATORY_FLOOR_YEARS_DEFAULT) -> dict | None:
    """If override drops below regulatory floor, emit alert. Else None.
    A value of 0 means retain-forever (never alerts)."""
    if retention_years == 0:
        return None
    if retention_years >= floor:
        return None
    severity = "critical" if retention_years < (floor // 2 or 1) else "warning"
    return emit_retention_alert(
        severity=severity, alert_type="override_below_regulatory_floor",
        tenant_schema=tenant_schema, target_table=target_table,
        retention_years=retention_years,
        reason=f"override_{retention_years}y_below_floor_{floor}y",
    )


def list_recent_retention_alerts(*, severity: str = "", limit: int = 50) -> list[dict]:
    """Return recent alerts, optionally filtered by severity."""
    with _ALERTS_LOCK:
        items = list(_ALERTS_RING)
    if severity:
        items = [a for a in items if a.get("severity") == severity]
    items.reverse()  # newest first
    return items[:limit]


def reset_retention_alerts() -> None:
    """Test-only."""
    with _ALERTS_LOCK:
        _ALERTS_RING.clear()


def retention_alerts_summary() -> dict:
    """Counts by severity. Never includes per-row content."""
    with _ALERTS_LOCK:
        items = list(_ALERTS_RING)
    by_sev = {"info": 0, "warning": 0, "critical": 0}
    for a in items:
        s = a.get("severity", "")
        if s in by_sev:
            by_sev[s] += 1
    return {"total": len(items), "by_severity": by_sev}
