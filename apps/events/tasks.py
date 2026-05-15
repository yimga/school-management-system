"""
Celery tasks and batch helpers for the canonical event/webhook runtime.
"""

from __future__ import annotations

from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.db import DatabaseError, IntegrityError, OperationalError
from django.utils import timezone

from apps.events.bus import dispatch_internal_subscribers
from apps.events.webhooks import (
    dispatch_due_webhooks,
    mark_event_processed,
    queue_deliveries_for_event,
)
from apps.platform_runtime.structured_logging import log_exception_with_context

# Typed exceptions for outbox processing (save, queue, mark); §2.4 broad-except policy.
_EVENT_OUTBOX_PROCESS_ERRORS = (
    IntegrityError,
    OperationalError,
    DatabaseError,
    ValidationError,
    ValueError,
    TypeError,
    OSError,
    ObjectDoesNotExist,
    AttributeError,
    KeyError,
)

try:
    from celery import shared_task
except ImportError:  # pragma: no cover - celery is optional in tests
    shared_task = None


def process_outbox_batch(batch_size: int = 100):
    from apps.events.models import DomainEvent

    # tenant-isolation-allow: domain-event outbox sweep across all tenants (reviewed 2026-05-14)
    queryset = DomainEvent.objects.filter(status=DomainEvent.Status.PENDING).order_by(
        "created_at"
    )[: max(1, int(batch_size))]
    processed = 0
    for event in queryset:
        try:
            event.status = DomainEvent.Status.PROCESSING
            event.save(update_fields=["status"])
            queue_deliveries_for_event(event, scheduled_for=timezone.now())
            dispatch_internal_subscribers(event)
            mark_event_processed(event)
            processed += 1
        except _EVENT_OUTBOX_PROCESS_ERRORS as exc:
            log_exception_with_context(
                "event outbox process failed",
                school_id=getattr(event, "school_id", None),
                extra={"event_id": str(event.id), "event_type": event.event_type},
            )
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
