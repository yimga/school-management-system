"""Tenant-scoped inventory reorder scan with live workflow telemetry."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def run_school_procurement_scan(school) -> dict[str, Any]:
    """Walk this school's inventory, pulse telemetry, and enqueue low-stock alerts.

    School-scoped on purpose — the platform-wide daily sweep stays a beat job
    and does not dump every tenant into one progress canvas.
    """
    summary: dict[str, Any] = {"scanned": 0, "low": 0, "enqueued": 0, "errors": 0}
    if school is None:
        return summary
    try:
        from django.db import connection

        from apps.platform_runtime.workflow_telemetry import (
            TASK_PROCUREMENT_LOOP,
            update_and_broadcast_progress,
        )
        from apps.platform_runtime.workflow_tracker import ensure_workflow_run
        from apps.schoolops.models import InventoryItem
        from apps.schoolops.tasks import notify_low_inventory_stock

        items = list(
            InventoryItem.objects.filter(school=school).order_by("pk")
        )
        expected = max(len(items), 1)
        schema = str(getattr(connection, "schema_name", "") or "")
        with ensure_workflow_run(
            "schoolops-procurement-scan",
            steps=("scan", "alert"),
            expected_duration_seconds=120,
            school_id=str(getattr(school, "pk", "") or ""),
            tenant_schema=schema,
            payload={"task_type": TASK_PROCUREMENT_LOOP},
        ):
            if not items:
                update_and_broadcast_progress(
                    school=school,
                    task_type=TASK_PROCUREMENT_LOOP,
                    processed=1,
                    expected=1,
                    log_message="No inventory rows to scan",
                    status="succeeded",
                )
                return summary
            for index, item in enumerate(items, start=1):
                summary["scanned"] += 1
                is_low = bool(getattr(item, "is_low", False))
                if is_low:
                    summary["low"] += 1
                    try:
                        notify_low_inventory_stock(inventory_item_id=item.pk)
                        summary["enqueued"] += 1
                    except Exception:  # noqa: BLE001
                        summary["errors"] += 1
                        logger.debug(
                            "procurement_scan_notify_failed item_id=%s",
                            item.pk,
                            exc_info=True,
                        )
                update_and_broadcast_progress(
                    school=school,
                    task_type=TASK_PROCUREMENT_LOOP,
                    processed=index,
                    expected=expected,
                    log_message=(
                        f"Scanned inventory row {index} of {expected}"
                        + (" (low stock)" if is_low else "")
                    ),
                )
        return summary
    except Exception:  # noqa: BLE001
        summary["errors"] += 1
        logger.debug("procurement_scan_failed", exc_info=True)
        return summary
