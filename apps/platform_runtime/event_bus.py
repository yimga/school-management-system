"""
Platform pub/sub event bus: persist → internal subscribers → webhook deliveries (async + retries).

- **Store**: :class:`~apps.platform_runtime.models.PlatformEvent` (proxy of ``PlatformEventLog``).
- **Publish**: :func:`publish_event`
- **Subscribe**: :func:`register_subscriber` (in-process handlers; register from ``AppConfig.ready``).
- **Webhooks**: :class:`~apps.platform_runtime.models.EventWebhookSubscription` + Celery delivery + DLQ.
- **Replay**: :func:`replay_event` (re-invokes subscribers and optionally webhooks for debugging).
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
from collections import defaultdict
from datetime import timedelta
from typing import Any, Callable, Dict, List, Optional

from django.utils import timezone

logger = logging.getLogger(__name__)

# event_type -> list of callables(payload, **kwargs)
_SUBSCRIBERS: Dict[str, List[Callable[..., Any]]] = defaultdict(list)

WEBHOOK_BACKOFF_SECONDS: tuple[int, ...] = (5, 30, 120, 600, 1800)
MAX_WEBHOOK_ATTEMPTS = 5


def register_subscriber(event_type: str, fn: Callable[..., Any]) -> None:
    """
    Register an in-process handler for ``event_type``.

    Use ``event_type="*"`` to receive all events. Handlers must not raise;
    exceptions are logged and swallowed.
    """
    key = (event_type or "").strip() or "*"
    if fn not in _SUBSCRIBERS[key]:
        _SUBSCRIBERS[key].append(fn)


def _notify_subscribers(
    row: Any,
    *,
    is_replay: bool,
) -> None:
    from apps.platform_runtime.models import PlatformEventLog

    if not isinstance(row, PlatformEventLog):
        return
    keys = [row.event_type, "*"]
    for k in keys:
        for fn in list(_SUBSCRIBERS.get(k, [])):
            try:
                fn(
                    row.payload,
                    event_type=row.event_type,
                    tenant_id=row.tenant_id or None,
                    school_id=row.school_id or None,
                    created_at=row.created_at,
                    event_id=row.pk,
                    is_replay=is_replay,
                )
            except Exception:
                logger.exception("event_bus subscriber failed event_type=%s fn=%s", k, fn)


def _subscription_matches_row(sub: Any, row: Any) -> bool:
    if sub.tenant_id and str(sub.tenant_id) != str(row.tenant_id or ""):
        return False
    if sub.school_id and str(sub.school_id) != str(row.school_id or ""):
        return False
    types_list = sub.event_types or []
    if types_list and row.event_type not in types_list:
        return False
    return True


def _enqueue_webhook_deliveries(row: Any) -> List[int]:
    from apps.platform_runtime.models import (
        EventWebhookDelivery,
        EventWebhookSubscription,
    )

    ids: List[int] = []
    for sub in EventWebhookSubscription.objects.filter(is_active=True):
        if not _subscription_matches_row(sub, row):
            continue
        if EventWebhookDelivery.objects.filter(
            subscription=sub, platform_event=row
        ).exists():
            continue
        d = EventWebhookDelivery.objects.create(
            subscription=sub,
            platform_event=row,
            status=EventWebhookDelivery.Status.PENDING,
        )
        ids.append(d.pk)
    return ids


def dispatch_event(
    row: Any,
    *,
    is_replay: bool = False,
    dispatch_webhooks: bool = True,
) -> None:
    """Fan-out one persisted row to subscribers and webhook queue."""
    _notify_subscribers(row, is_replay=is_replay)
    if not dispatch_webhooks:
        return
    delivery_ids = _enqueue_webhook_deliveries(row)
    if not delivery_ids:
        return
    from apps.platform_runtime.tasks import deliver_event_webhook_task

    for did in delivery_ids:
        deliver_event_webhook_task.delay(did)


def publish_event(
    event_type: str,
    payload: Dict[str, Any],
    *,
    tenant_id: Optional[str] = None,
    school_id: Optional[int] = None,
    idempotency_key: Optional[str] = None,
    strict_catalog: bool = True,
) -> Optional[Any]:
    """
    Persist the event and dispatch to subscribers + webhook subscriptions.

    When ``strict_catalog`` is False, types not in ``EVENT_CATALOG`` are still stored
    (integration / extension events).
    """
    from apps.platform_runtime.events import persist_platform_event

    row = persist_platform_event(
        event_type,
        payload,
        tenant_id=tenant_id,
        school_id=school_id,
        idempotency_key=idempotency_key,
        require_catalog=strict_catalog,
    )
    if row is None:
        return None
    dispatch_event(row, is_replay=False, dispatch_webhooks=True)
    return row


def replay_event(
    event_id: int,
    *,
    dispatch_webhooks: bool = True,
) -> dict[str, Any]:
    """
    Re-run subscribers (and optionally enqueue new webhook deliveries) for an existing log row.
    """
    from apps.platform_runtime.models import PlatformEventLog

    row = PlatformEventLog.objects.filter(pk=event_id).first()
    if row is None:
        return {"ok": False, "error": "not_found"}
    dispatch_event(row, is_replay=True, dispatch_webhooks=dispatch_webhooks)
    return {"ok": True, "event_id": row.pk, "event_type": row.event_type}


def deliver_webhook_attempt(delivery_id: int) -> dict[str, Any]:
    """
    Execute one HTTP POST for :class:`~apps.platform_runtime.models.EventWebhookDelivery`.
    Schedules Celery retry with backoff or marks dead-letter.
    """
    import requests

    from apps.platform_runtime.models import EventWebhookDelivery
    from apps.platform_runtime.tasks import deliver_event_webhook_task

    try:
        d = EventWebhookDelivery.objects.select_related("subscription").get(pk=delivery_id)
    except EventWebhookDelivery.DoesNotExist:
        return {"ok": False, "error": "missing_delivery"}

    if d.status in (
        EventWebhookDelivery.Status.DELIVERED,
        EventWebhookDelivery.Status.DEAD_LETTER,
    ):
        return {"ok": True, "skipped": d.status}

    sub = d.subscription
    ev = d.platform_event
    body_obj = {
        "event_type": ev.event_type,
        "payload": ev.payload,
        "tenant_id": ev.tenant_id or None,
        "school_id": ev.school_id or None,
        "event_id": ev.pk,
        "created_at": ev.created_at.isoformat() if ev.created_at else None,
        "delivery_id": d.pk,
        "attempt": d.attempt_count + 1,
    }
    raw = json.dumps(body_obj, separators=(",", ":"), default=str)
    headers = {
        "Content-Type": "application/json",
        "X-RMC-Event-Id": str(ev.pk),
        "X-RMC-Delivery-Id": str(d.pk),
    }
    if sub.secret:
        sig = hmac.new(
            sub.secret.encode("utf-8"),
            raw.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        headers["X-RMC-Signature"] = sig

    d.attempt_count += 1
    d.status = EventWebhookDelivery.Status.DELIVERING
    d.save(update_fields=["attempt_count", "status", "updated_at"])

    try:
        r = requests.post(
            sub.target_url,
            data=raw.encode("utf-8"),
            headers=headers,
            timeout=15,
        )
        d.last_http_status = r.status_code
        if 200 <= r.status_code < 300:
            d.status = EventWebhookDelivery.Status.DELIVERED
            d.delivered_at = timezone.now()
            d.last_error = ""
            d.next_retry_at = None
            d.save(
                update_fields=[
                    "status",
                    "delivered_at",
                    "last_http_status",
                    "last_error",
                    "next_retry_at",
                    "updated_at",
                ]
            )
            return {"ok": True, "status": "delivered", "http": r.status_code}
        err_txt = (r.text or "")[:2000]
        d.last_error = f"HTTP {r.status_code}: {err_txt}"
    except Exception as e:
        d.last_http_status = None
        d.last_error = str(e)[:2000]

    if d.attempt_count >= MAX_WEBHOOK_ATTEMPTS:
        d.status = EventWebhookDelivery.Status.DEAD_LETTER
        d.next_retry_at = None
        d.save(
            update_fields=[
                "status",
                "last_http_status",
                "last_error",
                "next_retry_at",
                "updated_at",
            ]
        )
        return {"ok": False, "status": "dead_letter"}

    d.status = EventWebhookDelivery.Status.PENDING
    idx = min(d.attempt_count - 1, len(WEBHOOK_BACKOFF_SECONDS) - 1)
    delay = WEBHOOK_BACKOFF_SECONDS[max(0, idx)]
    d.next_retry_at = timezone.now() + timedelta(seconds=delay)
    d.save(
        update_fields=[
            "status",
            "last_http_status",
            "last_error",
            "next_retry_at",
            "updated_at",
        ]
    )
    deliver_event_webhook_task.apply_async(args=[delivery_id], countdown=delay)
    return {"ok": False, "status": "retry_scheduled", "delay": delay}


def sweep_stale_webhook_deliveries(limit: int = 50) -> int:
    """Safety net: pick PENDING rows past ``next_retry_at`` and re-queue (clock skew / lost tasks)."""
    from apps.platform_runtime.models import EventWebhookDelivery
    from apps.platform_runtime.tasks import deliver_event_webhook_task

    now = timezone.now()
    qs = (
        EventWebhookDelivery.objects.filter(
            status=EventWebhookDelivery.Status.PENDING,
            next_retry_at__lte=now,
        )
        .order_by("next_retry_at")[:limit]
    )
    n = 0
    for d in qs:
        deliver_event_webhook_task.delay(d.pk)
        n += 1
    return n
