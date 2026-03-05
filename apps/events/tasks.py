"""
Celery task to consume the event outbox: process pending events and dispatch to handlers/webhooks.
Run periodically or on-demand; supports retries and idempotency.
"""
from django.utils import timezone

try:
    from celery import shared_task
except ImportError:
    shared_task = None


def process_outbox_batch(batch_size: int = 100):
    """
    Process up to `batch_size` pending domain events. Mark as processing, run handlers, then mark processed/failed.
    Call from a Celery task or management command.
    """
    from apps.events.models import DomainEvent

    qs = (
        DomainEvent.objects.filter(status=DomainEvent.Status.PENDING)
        .order_by("created_at")[:batch_size]
    )
    processed = 0
    for event in qs:
        try:
            event.status = DomainEvent.Status.PROCESSING
            event.save(update_fields=["status"])
            _dispatch_event(event)
            event.status = DomainEvent.Status.PROCESSED
            event.processed_at = timezone.now()
            event.save(update_fields=["status", "processed_at"])
            processed += 1
        except Exception as e:
            event.status = DomainEvent.Status.FAILED
            event.retry_count += 1
            event.error_message = str(e)[:2000]
            event.save(update_fields=["status", "retry_count", "error_message"])
    return processed


def _dispatch_event(event):
    """
    Dispatch a single event: create WebhookDelivery records for matching subscriptions.
    Actual HTTP delivery is done by process_webhook_deliveries_batch() (retries, signing).
    """
    from django.db.models import Q
    from apps.events.models import DomainEvent, WebhookSubscription, WebhookDelivery

    if not isinstance(event, DomainEvent):
        return
    subs = WebhookSubscription.objects.filter(is_active=True)
    # Tenant scope: subscription.school_id is None (platform) or matches event.school_id
    if event.school_id is not None:
        subs = subs.filter(Q(school_id__isnull=True) | Q(school_id=event.school_id))
    else:
        subs = subs.filter(school_id__isnull=True)
    event_type = getattr(event, "event_type", None) or ""
    for sub in subs:
        types_list = sub.event_types if isinstance(sub.event_types, list) else []
        if types_list and event_type not in types_list:
            continue
        WebhookDelivery.objects.get_or_create(
            subscription=sub,
            domain_event=event,
            defaults={"status": WebhookDelivery.Status.PENDING},
        )


def process_webhook_deliveries_batch(batch_size: int = 50):
    """
    POST pending WebhookDelivery records to subscription URLs with retries and HMAC signing.
    Call from Celery or process_event_outbox after processing outbox.
    """
    import hashlib
    import hmac
    import json
    from django.utils import timezone
    from urllib.request import Request, urlopen
    from urllib.error import HTTPError, URLError

    from apps.events.models import WebhookDelivery

    qs = (
        WebhookDelivery.objects.filter(status=WebhookDelivery.Status.PENDING)
        .select_related("subscription", "domain_event")[:batch_size]
    )
    processed = 0
    for delivery in qs:
        sub = delivery.subscription
        event = delivery.domain_event
        body = json.dumps({"event_type": event.event_type, "payload": event.payload}).encode("utf-8")
        idempotency_key = f"{delivery.id}-{event.id}-{delivery.retry_count}"
        headers = {"Content-Type": "application/json", "X-Webhook-Idempotency-Key": idempotency_key}
        if sub.secret:
            sig = hmac.new(sub.secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
            headers["X-Webhook-Signature"] = f"sha256={sig}"
        try:
            req = Request(sub.url, data=body, headers=headers, method="POST")
            resp = urlopen(req, timeout=30)
            delivery.status = WebhookDelivery.Status.DELIVERED
            delivery.http_status = resp.getcode()
            delivery.delivered_at = timezone.now()
            delivery.attempted_at = delivery.attempted_at or delivery.delivered_at
            delivery.idempotency_key = idempotency_key
            delivery.save(update_fields=["status", "http_status", "delivered_at", "attempted_at", "idempotency_key"])
            processed += 1
        except (HTTPError, URLError, OSError) as e:
            delivery.retry_count += 1
            delivery.attempted_at = timezone.now()
            delivery.error_message = str(e)[:2000]
            delivery.http_status = getattr(e, "code", None)
            delivery.status = WebhookDelivery.Status.FAILED if delivery.retry_count >= 3 else WebhookDelivery.Status.PENDING
            delivery.save(update_fields=["retry_count", "attempted_at", "error_message", "http_status", "status"])
            processed += 1
    return processed


if shared_task is not None:

    @shared_task(name="apps.events.process_event_outbox")
    def process_event_outbox_task(batch_size: int = 100):
        """Celery task: process pending domain events from the outbox. Schedule via beat."""
        return process_outbox_batch(batch_size=batch_size)
