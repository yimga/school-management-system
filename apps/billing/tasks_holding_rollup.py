"""Celery beat entry — materialize holding-company currency rollups (B4)."""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

try:
    from celery import shared_task

    @shared_task(name="apps.billing.materialize_holding_currency_rollups")
    def materialize_holding_currency_rollups_task() -> dict:
        """Refresh every holding company's per-currency rollup buckets."""
        from apps.billing.holding_rollup import materialize_all_holding_currency_rollups

        summary = materialize_all_holding_currency_rollups()
        summary["status"] = "ok"
        logger.info("holding currency rollup beat: %s", summary)
        return summary

except ImportError:  # pragma: no cover - celery optional at import time
    materialize_holding_currency_rollups_task = None  # type: ignore[assignment]
