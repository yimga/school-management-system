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


# A domain event that blew up mid-sweep used to be flipped to FAILED and left
# there forever: the sweep selected `status=PENDING` only, so `retry_count` was
# incremented by a field nothing ever read again. One transient IntegrityError /
# OperationalError therefore dead-lettered the event permanently — no webhook
# delivery, no internal subscriber, no automation, and no operator signal short of
# reading the table by hand. FAILED rows under this attempt ceiling are redriven on
# the next sweep; past it the row stays FAILED and is a genuine dead letter.
#
# Redrive is safe against double effects: `queue_deliveries_for_event` reuses the
# existing (subscription, event) delivery rather than creating a second one, and
# `automation.domain_event_bridge` dedups on the event pk via a 24h cache key, so a
# redriven event cannot re-fire a workflow that already ran for it.
MAX_OUTBOX_ATTEMPTS = 3


def process_outbox_batch(batch_size: int = 100):
    from django.db.models import Q

    from apps.events.models import DomainEvent

    # tenant-isolation-allow: domain-event outbox sweep across all tenants (reviewed 2026-05-14)
    queryset = list(
        DomainEvent.objects.filter(
            Q(status=DomainEvent.Status.PENDING)
            | Q(
                status=DomainEvent.Status.FAILED,
                retry_count__lt=MAX_OUTBOX_ATTEMPTS,
            )
        )
        .order_by("created_at")[: max(1, int(batch_size))]
    )
    school_ids = {e.school_id for e in queryset if getattr(e, "school_id", None)}
    school_by_id: dict = {}
    if school_ids:
        from apps.schools.models import School

        school_by_id = {
            s.pk: s
            for s in School.objects.filter(pk__in=school_ids).only(  # tenant-isolation-allow: celery-events-beat-school-id-list-scoped
                "pk", "slug", "subdomain", "is_active"
            )
        }
    processed = 0
    for event in queryset:
        if getattr(event, "school_id", None) and event.school_id in school_by_id:
            event._prefetched_school = school_by_id[event.school_id]  # noqa: SLF001
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
