from __future__ import annotations

import hashlib
import hmac
import json
from datetime import timedelta
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from uuid import uuid4

from django.db.models import Q
from django.utils import timezone


RETRY_BACKOFF_SECONDS = (60, 300, 3600)
RETRY_BACKOFF_FALLBACK = 21600


def canonical_json_bytes(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")


def sign_payload(secret: str, payload_bytes: bytes) -> str:
    digest = hmac.new((secret or "").encode("utf-8"), payload_bytes, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def _next_retry_at(now, retry_count: int):
    if retry_count <= 0:
        delay = RETRY_BACKOFF_SECONDS[0]
    elif retry_count <= len(RETRY_BACKOFF_SECONDS):
        delay = RETRY_BACKOFF_SECONDS[retry_count - 1]
    else:
        delay = RETRY_BACKOFF_FALLBACK
    return now + timedelta(seconds=delay)


def webhook_envelope_for_event(event) -> dict[str, Any]:
    payload = event.payload if isinstance(event.payload, dict) else {}
    emitted_at = getattr(event, "created_at", None) or timezone.now()
    return {
        "event_id": str(event.id),
        "event_type": str(getattr(event, "event_type", "") or ""),
        "school_id": str(getattr(event, "school_id", "") or "") or None,
        "schema_name": getattr(event, "schema_name", None),
        "emitted_at": emitted_at.isoformat() if emitted_at else None,
        "data": payload,
    }


def build_webhook_body(event) -> bytes:
    return canonical_json_bytes(webhook_envelope_for_event(event))


def _default_http_post(url: str, body: bytes, headers: dict[str, str], timeout: int = 30) -> tuple[int, str]:
    request = Request(url, data=body, headers=headers, method="POST")
    try:
        with urlopen(request, timeout=timeout) as response:
            return int(response.getcode() or 200), response.read().decode("utf-8", errors="replace")
    except HTTPError as exc:
        try:
            detail = exc.read().decode("utf-8", errors="replace")
        except Exception:
            detail = str(exc)
        return int(exc.code or 500), detail
    except URLError as exc:
        return 0, str(exc.reason)
    except Exception as exc:  # pragma: no cover - defensive branch
        return 0, str(exc)


def _normalize_event_types(raw) -> list[str]:
    if not isinstance(raw, list):
        return []
    return [str(item or "").strip() for item in raw if str(item or "").strip()]


def _subscription_matches_event(subscription, event_type: str) -> bool:
    configured = _normalize_event_types(getattr(subscription, "event_types", None))
    if not configured:
        return True
    return "*" in configured or event_type in configured


def matching_subscriptions_for_event(event):
    from apps.events.models import WebhookSubscription

    subscriptions = WebhookSubscription.objects.filter(is_active=True)
    school_id = getattr(event, "school_id", None)
    if school_id:
        subscriptions = subscriptions.filter(Q(school_id__isnull=True) | Q(school_id=school_id))
    else:
        subscriptions = subscriptions.filter(school_id__isnull=True)
    event_type = str(getattr(event, "event_type", "") or "")
    return [item for item in subscriptions.order_by("created_at", "id") if _subscription_matches_event(item, event_type)]


def queue_deliveries_for_event(event, *, scheduled_for=None) -> list:
    from apps.events.models import WebhookDelivery

    due_at = scheduled_for or timezone.now()
    deliveries = []
    for subscription in matching_subscriptions_for_event(event):
        delivery = (
            WebhookDelivery.objects.filter(subscription=subscription, domain_event=event)
            .order_by("id")
            .first()
        )
        if delivery is None:
            delivery = WebhookDelivery.objects.create(
                subscription=subscription,
                domain_event=event,
                status=WebhookDelivery.Status.PENDING,
                scheduled_for=due_at,
                max_attempts=4,
            )
        elif delivery.status == WebhookDelivery.Status.PENDING and delivery.scheduled_for is None:
            delivery.scheduled_for = due_at
            delivery.save(update_fields=["scheduled_for"])
        deliveries.append(delivery)
    return deliveries


def mark_event_processed(event, *, processed_at=None):
    from apps.events.models import DomainEvent

    finished_at = processed_at or timezone.now()
    if getattr(event, "status", None) == DomainEvent.Status.PROCESSED and getattr(event, "processed_at", None):
        return event
    event.status = DomainEvent.Status.PROCESSED
    event.processed_at = finished_at
    event.save(update_fields=["status", "processed_at"])
    return event


def enqueue_webhook_event(
    *,
    school=None,
    event_type: str,
    data: dict[str, Any] | None = None,
    event_id: str | None = None,
    schema_name: str | None = None,
    process_immediately: bool = True,
) -> list:
    from apps.events.models import DomainEvent

    normalized_event_type = str(event_type or "").strip()
    if not normalized_event_type:
        return []

    payload = data or {}
    idempotency_key = str(event_id or uuid4().hex)
    school_id = getattr(school, "pk", None) or getattr(school, "id", None)
    schema_name = schema_name or getattr(getattr(school, "client", None), "schema_name", None) or getattr(school, "schema_name", None)
    now = timezone.now()
    event, created = DomainEvent.objects.get_or_create(
        idempotency_key=idempotency_key,
        defaults={
            "event_type": normalized_event_type,
            "payload": payload,
            "school_id": school_id,
            "schema_name": schema_name,
            "status": DomainEvent.Status.PENDING,
        },
    )
    if not created and process_immediately:
        existing = list(event.webhook_deliveries.select_related("subscription").all())
        if existing:
            return existing
    deliveries = queue_deliveries_for_event(event, scheduled_for=now) if process_immediately else []
    if process_immediately:
        mark_event_processed(event, processed_at=now)
    return deliveries


def deliver_webhook_delivery(
    delivery,
    *,
    http_post: Callable[[str, bytes, dict[str, str], int], tuple[int, str]] | None = None,
    now=None,
) -> dict[str, Any]:
    from apps.events.models import WebhookDelivery

    now = now or timezone.now()
    http_post = http_post or _default_http_post

    if delivery.status == WebhookDelivery.Status.DELIVERED:
        return {"delivery_id": delivery.pk, "status": delivery.status, "skipped": True}
    if delivery.scheduled_for and now < delivery.scheduled_for:
        return {"delivery_id": delivery.pk, "status": delivery.status, "skipped": True}

    event = delivery.domain_event
    body = build_webhook_body(event)
    idempotency_key = f"{delivery.id}-{event.id}-{delivery.retry_count}"
    headers = {
        "Content-Type": "application/json",
        "X-Webhook-Event": str(getattr(event, "event_type", "") or ""),
        "X-Webhook-Event-Id": str(event.id),
        "X-Webhook-Idempotency-Key": idempotency_key,
        "X-Webhook-Signature": sign_payload(delivery.subscription.secret or "", body),
    }
    try:
        status_code, detail = http_post(delivery.subscription.url, body, headers, 30)
        if not (200 <= int(status_code) < 300):
            raise HTTPError(delivery.subscription.url, int(status_code or 500), str(status_code), hdrs=None, fp=None)
        delivery.status = WebhookDelivery.Status.DELIVERED
        delivery.http_status = int(status_code or 200)
        delivery.attempted_at = now
        delivery.delivered_at = now
        delivery.scheduled_for = None
        delivery.idempotency_key = idempotency_key
        delivery.error_message = ""
        delivery.save(
            update_fields=[
                "status",
                "http_status",
                "attempted_at",
                "delivered_at",
                "scheduled_for",
                "idempotency_key",
                "error_message",
            ]
        )
        return {
            "delivery_id": delivery.pk,
            "status": delivery.status,
            "attempts": delivery.retry_count,
            "http_status": delivery.http_status,
            "detail": detail,
        }
    except (HTTPError, URLError, OSError) as exc:
        delivery.retry_count += 1
        delivery.attempted_at = now
        delivery.http_status = getattr(exc, "code", None)
        delivery.error_message = str(exc)[:2000]
        delivery.idempotency_key = idempotency_key
        if delivery.retry_count >= max(1, int(delivery.max_attempts or 4)):
            delivery.status = WebhookDelivery.Status.FAILED
            delivery.scheduled_for = None
        else:
            delivery.status = WebhookDelivery.Status.PENDING
            delivery.scheduled_for = _next_retry_at(now, delivery.retry_count)
        delivery.save(
            update_fields=[
                "retry_count",
                "attempted_at",
                "http_status",
                "error_message",
                "idempotency_key",
                "status",
                "scheduled_for",
            ]
        )
        return {
            "delivery_id": delivery.pk,
            "status": delivery.status,
            "attempts": delivery.retry_count,
            "http_status": delivery.http_status,
            "detail": delivery.error_message,
        }


def dispatch_due_webhooks(
    *,
    limit: int = 100,
    now=None,
    http_post: Callable[[str, bytes, dict[str, str], int], tuple[int, str]] | None = None,
) -> list[dict[str, Any]]:
    from apps.events.models import WebhookDelivery

    now = now or timezone.now()
    due = (
        WebhookDelivery.objects.filter(status=WebhookDelivery.Status.PENDING)
        .filter(Q(scheduled_for__isnull=True) | Q(scheduled_for__lte=now))
        .select_related("subscription", "domain_event")
        .order_by("scheduled_for", "created_at")[: max(1, int(limit))]
    )
    return [deliver_webhook_delivery(item, http_post=http_post, now=now) for item in due]


def replay_webhook_delivery(delivery, *, new_event_id: str | None = None):
    from apps.events.models import DomainEvent, WebhookDelivery

    event = DomainEvent.objects.create(
        event_type=delivery.domain_event.event_type,
        payload=delivery.domain_event.payload,
        school_id=delivery.domain_event.school_id,
        schema_name=delivery.domain_event.schema_name,
        status=DomainEvent.Status.PROCESSED,
        processed_at=timezone.now(),
        idempotency_key=str(new_event_id or f"{delivery.domain_event.id}-replay-{uuid4().hex[:8]}"),
    )
    return WebhookDelivery.objects.create(
        subscription=delivery.subscription,
        domain_event=event,
        status=WebhookDelivery.Status.PENDING,
        scheduled_for=timezone.now(),
        max_attempts=delivery.max_attempts,
    )
