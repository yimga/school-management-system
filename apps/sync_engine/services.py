"""
Offline-first sync engine: pending rows, remote apply, retries, visible sync state.

Queue storage uses apps.api.mobile_api.OfflineSyncQueue (device-scoped replay API).
"""

from __future__ import annotations

from typing import Any

from django.db.models import Count


def get_pending_changes(
    school_id: int | None,
    user_id: int,
    device_id: str | None = None,
) -> list[dict[str, Any]]:
    """
    Return offline mutations not yet settled (pending retry or awaiting replay).

    Each item: ``entity``, ``queue_id``, ``action``, ``status``, ``payload``.
    ``school_id`` filters payloads that declare ``school_id`` when present.
    """
    from apps.api.mobile_api import MobileDevice, OfflineSyncQueue

    device_filter: dict[str, Any] = {"user_id": user_id}
    if device_id:
        device_filter["device_id"] = device_id
    device_ids = MobileDevice.objects.filter(**device_filter).values_list(
        "id", flat=True
    )
    qs = OfflineSyncQueue.objects.filter(
        device_id__in=device_ids,
        status__in=["PENDING", "SYNCING", "FAILED"],
    ).order_by("created_at")
    out: list[dict[str, Any]] = []
    for row in qs:
        payload = row.data or {}
        if school_id is not None:
            psid = payload.get("school_id")
            if psid is not None and str(psid) != str(school_id):
                continue
        out.append(
            {
                "entity": row.entity_type,
                "queue_id": row.id,
                "action": row.action,
                "status": row.status,
                "retry_count": getattr(row, "retry_count", 0),
                "payload": payload,
                "client_timestamp": row.client_timestamp.isoformat()
                if row.client_timestamp
                else None,
            }
        )
    return out


def apply_remote(
    school_id: int,
    user_id: int,
    remote_changes: list[dict[str, Any]],
    *,
    device_id: str | None = None,
) -> dict[str, Any]:
    """
    Validate a batch of remote deltas. Detect duplicate entity operations (conflicts).

    Returns ``applied`` (logical rows accepted) and ``conflicts`` (duplicate keys).
    """
    applied = 0
    conflicts: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for change in remote_changes:
        entity = str(change.get("entity") or change.get("entity_type") or "")
        eid = str(change.get("id") or change.get("entity_id") or "")
        key = (entity, eid)
        if key in seen and entity and eid:
            conflicts.append(
                {
                    "reason": "duplicate_remote_operation",
                    "entity": entity,
                    "id": eid,
                }
            )
            continue
        if entity and eid:
            seen.add(key)
        applied += 1
    return {
        "applied": applied,
        "conflicts": conflicts,
        "school_id": school_id,
        "user_id": user_id,
        "device_id": device_id,
    }


def get_visible_sync_state(user_id: int) -> dict[str, Any]:
    """Aggregate counts for UI: pending, failed, conflicts, completed (recent window optional)."""
    from apps.api.mobile_api import MobileDevice, OfflineSyncQueue

    device_ids = MobileDevice.objects.filter(user_id=user_id).values_list(
        "id", flat=True
    )
    rows = (
        OfflineSyncQueue.objects.filter(device_id__in=device_ids)
        .values("status")
        .annotate(total=Count("id"))
    )
    by_status = {r["status"]: r["total"] for r in rows}
    return {
        "pending": by_status.get("PENDING", 0) + by_status.get("SYNCING", 0),
        "failed": by_status.get("FAILED", 0),
        "conflicts": by_status.get("CONFLICT", 0),
        "completed": by_status.get("COMPLETED", 0),
        "by_status": by_status,
    }


def retry_failed_sync_items(
    user_id: int,
    *,
    max_retries: int = 5,
) -> dict[str, int]:
    """
    Reset FAILED queue rows so the client can POST ``sync_batch`` again.

    Increments ``retry_count``; skips rows at or above ``max_retries``.
    """
    from apps.api.mobile_api import MobileDevice, OfflineSyncQueue

    device_ids = MobileDevice.objects.filter(user_id=user_id).values_list(
        "id", flat=True
    )
    qs = OfflineSyncQueue.objects.filter(device_id__in=device_ids, status="FAILED")
    retried = 0
    skipped = 0
    for item in list(qs):
        rc = getattr(item, "retry_count", 0) or 0
        if rc >= max_retries:
            skipped += 1
            continue
        item.retry_count = rc + 1
        item.status = "PENDING"
        item.error_message = ""
        item.synced_at = None
        item.save(
            update_fields=[
                "retry_count",
                "status",
                "error_message",
                "synced_at",
            ]
        )
        retried += 1
    return {"retried": retried, "skipped_max_retries": skipped}
