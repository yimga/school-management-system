"""Outbound webhook delivery services with retry, dead-letter, and replay helpers."""

from __future__ import annotations

import hashlib
import hmac
import json
from datetime import timedelta
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from uuid import uuid4

from django.utils import timezone

from apps.siteconfig.models import WebhookDelivery, WebhookSubscription

# Retry schedule: 1m, 5m, 1h, then 6h cap for remaining attempts.
RETRY_BACKOFF_SECONDS = (60, 300, 3600)
RETRY_BACKOFF_FALLBACK = 21600


def canonical_json_bytes(payload: dict[str, Any]) -> bytes:
    """Serialize payload deterministically for signature + transport."""
    return json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")


def sign_payload(secret: str, payload_bytes: bytes) -> str:
    """HMAC SHA-256 signature with webhook-style prefix."""
    key = (secret or "").encode("utf-8")
    digest = hmac.new(key, payload_bytes, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def _next_retry_at(now, attempts: int):
    if attempts <= 0:
        delay = RETRY_BACKOFF_SECONDS[0]
    elif attempts <= len(RETRY_BACKOFF_SECONDS):
        delay = RETRY_BACKOFF_SECONDS[attempts - 1]
    else:
        delay = RETRY_BACKOFF_FALLBACK
    return now + timedelta(seconds=delay)


def _build_envelope(*, school_id: str, event_type: str, event_id: str, data: dict[str, Any]) -> dict[str, Any]:
    return {
        "event_id": event_id,
        "event_type": event_type,
        "school_id": str(school_id),
        "emitted_at": timezone.now().isoformat(),
        "data": data,
    }


def enqueue_webhook_event(
    *,
    school,
    event_type: str,
    data: dict[str, Any] | None = None,
    event_id: str | None = None,
) -> list[WebhookDelivery]:
    """
    Enqueue an outbound event for active subscriptions.

    Idempotency: subscription + event_id is unique. If an entry already exists, it is reused.
    """
    if school is None:
        return []

    event_type = str(event_type or "").strip()
    if not event_type:
        return []

    data = data or {}
    event_id = str(event_id or uuid4().hex)
    now = timezone.now()
    deliveries: list[WebhookDelivery] = []

    subscriptions = WebhookSubscription.objects.filter(
        school=school,
        is_active=True,
    ).filter(event_type__in=[event_type, "*"])

    for sub in subscriptions:
        envelope = _build_envelope(
            school_id=str(school.pk),
            event_type=event_type,
            event_id=event_id,
            data=data,
        )
        body = canonical_json_bytes(envelope)
        signature = sign_payload(sub.secret or "", body)
        delivery, created = WebhookDelivery.objects.get_or_create(
            subscription=sub,
            event_id=event_id,
            defaults={
                "event_type": event_type,
                "payload": envelope,
                "signature": signature,
                "status": WebhookDelivery.Status.PENDING,
                "attempts": 0,
                "max_attempts": 4,
                "next_attempt_at": now,
            },
        )
        if not created and delivery.status in {
            WebhookDelivery.Status.PENDING,
            WebhookDelivery.Status.RETRYING,
        }:
            delivery.payload = envelope
            delivery.signature = signature
            if delivery.next_attempt_at is None:
                delivery.next_attempt_at = now
            delivery.save(update_fields=["payload", "signature", "next_attempt_at", "updated_at"])
        deliveries.append(delivery)

    return deliveries


def _default_http_post(url: str, body: bytes, headers: dict[str, str], timeout: int = 10) -> tuple[int, str]:
    req = Request(url, data=body, headers=headers, method="POST")
    try:
        with urlopen(req, timeout=timeout) as resp:
            return int(resp.getcode() or 200), resp.read().decode("utf-8", errors="replace")
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


def deliver_webhook_delivery(
    delivery: WebhookDelivery,
    *,
    http_post: Callable[[str, bytes, dict[str, str]], tuple[int, str]] | None = None,
    now=None,
) -> dict[str, Any]:
    """
    Attempt one delivery operation and update retry/dead-letter state.
    """
    now = now or timezone.now()
    http_post = http_post or _default_http_post

    if delivery.status in {WebhookDelivery.Status.DELIVERED, WebhookDelivery.Status.DEAD_LETTER}:
        return {"delivery_id": delivery.pk, "status": delivery.status, "skipped": True}
    if delivery.next_attempt_at and now < delivery.next_attempt_at:
        return {"delivery_id": delivery.pk, "status": delivery.status, "skipped": True}

    payload = delivery.payload or {}
    body = canonical_json_bytes(payload)

    headers = {
        "Content-Type": "application/json",
        "X-Webhook-Event": delivery.event_type,
        "X-Webhook-Event-Id": delivery.event_id,
        "X-Webhook-Signature": delivery.signature or sign_payload(delivery.subscription.secret or "", body),
    }
    status_code, detail = http_post(delivery.subscription.target_url, body, headers)

    delivery.attempts += 1
    delivery.last_attempt_at = now
    delivery.last_status_code = status_code if status_code > 0 else None

    if 200 <= status_code < 300:
        delivery.status = WebhookDelivery.Status.DELIVERED
        delivery.delivered_at = now
        delivery.next_attempt_at = None
        delivery.last_error = ""
    elif delivery.attempts >= max(1, int(delivery.max_attempts or 1)):
        delivery.status = WebhookDelivery.Status.DEAD_LETTER
        delivery.next_attempt_at = None
        delivery.last_error = detail[:1000]
    else:
        delivery.status = WebhookDelivery.Status.RETRYING
        delivery.next_attempt_at = _next_retry_at(now, delivery.attempts)
        delivery.last_error = detail[:1000]

    delivery.save(
        update_fields=[
            "attempts",
            "last_attempt_at",
            "last_status_code",
            "status",
            "delivered_at",
            "next_attempt_at",
            "last_error",
            "updated_at",
        ]
    )

    return {
        "delivery_id": delivery.pk,
        "status": delivery.status,
        "attempts": delivery.attempts,
        "http_status": status_code,
        "detail": detail,
    }


def dispatch_due_webhooks(
    *,
    limit: int = 100,
    now=None,
    http_post: Callable[[str, bytes, dict[str, str]], tuple[int, str]] | None = None,
) -> list[dict[str, Any]]:
    """Dispatch pending/retrying deliveries whose next_attempt_at is due."""
    now = now or timezone.now()
    due = (
        WebhookDelivery.objects.select_related("subscription")
        .filter(status__in=[WebhookDelivery.Status.PENDING, WebhookDelivery.Status.RETRYING])
        .filter(next_attempt_at__lte=now)
        .order_by("next_attempt_at", "created_at")[: max(1, int(limit))]
    )
    return [deliver_webhook_delivery(item, http_post=http_post, now=now) for item in due]


def replay_webhook_delivery(delivery: WebhookDelivery, *, new_event_id: str | None = None) -> WebhookDelivery:
    """
    Clone a delivery into a fresh pending event for replay.
    """
    new_id = str(new_event_id or f"{delivery.event_id}-replay-{uuid4().hex[:8]}")
    clone = WebhookDelivery.objects.create(
        subscription=delivery.subscription,
        event_id=new_id,
        event_type=delivery.event_type,
        payload=delivery.payload,
        signature=delivery.signature,
        status=WebhookDelivery.Status.PENDING,
        attempts=0,
        max_attempts=delivery.max_attempts,
        next_attempt_at=timezone.now(),
    )
    return clone

