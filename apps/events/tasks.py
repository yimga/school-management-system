"""
Celery tasks and batch helpers for the canonical event/webhook runtime.
"""
from __future__ import annotations

from django.utils import timezone

from apps.events.webhooks import (
    dispatch_due_webhooks,
    mark_event_processed,
    queue_deliveries_for_event,
)

try:
    from celery import shared_task
except ImportError:  # pragma: no cover - celery is optional in tests
    shared_task = None


def process_outbox_batch(batch_size: int = 100):
    from apps.events.models import DomainEvent

    queryset = (
        DomainEvent.objects.filter(status=DomainEvent.Status.PENDING)
        .order_by("created_at")[: max(1, int(batch_size))]
    )
    processed = 0
    for event in queryset:
        try:
            event.status = DomainEvent.Status.PROCESSING
            event.save(update_fields=["status"])
            queue_deliveries_for_event(event, scheduled_for=timezone.now())
            mark_event_processed(event)
            processed += 1
        except Exception as exc:
            event.status = DomainEvent.Status.FAILED
            event.retry_count += 1
            event.error_message = str(exc)[:2000]
            event.save(update_fields=["status", "retry_count", "error_message"])
    return processed


def process_webhook_deliveries_batch(batch_size: int = 50, *, now=None, http_post=None):
    results = dispatch_due_webhooks(limit=batch_size, now=now, http_post=http_post)
    return len(results)


if shared_task is not None:

    @shared_task(name="apps.events.process_event_outbox")
    def process_event_outbox_task(batch_size: int = 100):
        return process_outbox_batch(batch_size=batch_size)

    @shared_task(name="apps.events.process_webhook_deliveries")
    def process_webhook_deliveries_task(batch_size: int = 50):
        return process_webhook_deliveries_batch(batch_size=batch_size)
