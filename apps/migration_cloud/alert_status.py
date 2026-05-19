"""v3.40.0 Agent 12 — Command Center status summary for operator alerts.

Exposes a single ``get_alert_status_summary()`` callable that the
Command Center view can defensively import + render. Kept in its own
module so Agent 6's view file does NOT need to change in this wave —
Agent 6 (or v3.41) wires the call site.

Sample::

    try:
        from apps.migration_cloud.alert_status import get_alert_status_summary
        alert_status = get_alert_status_summary()
    except Exception:
        alert_status = None
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


def get_alert_status_summary() -> dict:
    """Return a small dict the Command Center can render in a card.

    Never raises — returns a defensive empty-ish dict on any error so
    the operator UI still renders.
    """
    try:
        from apps.migration_cloud import alerts
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning(
            "alert_status_summary_import_failed err_type=%s",
            type(exc).__name__,
        )
        return {
            "last_critical_alert_at": None,
            "active_dedup_keys": 0,
            "channels_enabled": ["log"],
            "dry_run": True,
            "rate_limit_per_hour": 50,
        }

    try:
        active_count, oldest_monotonic = alerts._snapshot_dedupe_state()
    except Exception:  # pragma: no cover - defensive
        active_count, oldest_monotonic = 0, None

    last_critical_at: datetime | None = None
    if oldest_monotonic is not None:
        # Translate monotonic-clock seconds back to wall-clock by anchoring
        # against ``time.monotonic()`` / ``time.time()`` at call time. Best-
        # effort — used only as a display hint, not as a source of truth.
        delta_seconds = max(0.0, time.monotonic() - oldest_monotonic)
        try:
            wall = time.time() - delta_seconds
            last_critical_at = datetime.fromtimestamp(wall, tz=timezone.utc)
        except Exception:  # pragma: no cover - defensive
            last_critical_at = None

    try:
        channels = alerts._channels_enabled()
    except Exception:  # pragma: no cover - defensive
        channels = ["log"]
    try:
        dry_run = alerts._is_dry_run()
    except Exception:  # pragma: no cover - defensive
        dry_run = True
    try:
        rate_limit = alerts._get_rate_limit_per_hour()
    except Exception:  # pragma: no cover - defensive
        rate_limit = 50

    return {
        "last_critical_alert_at": last_critical_at,
        "active_dedup_keys": int(active_count),
        "channels_enabled": list(channels),
        "dry_run": bool(dry_run),
        "rate_limit_per_hour": int(rate_limit),
    }


__all__ = ["get_alert_status_summary"]
