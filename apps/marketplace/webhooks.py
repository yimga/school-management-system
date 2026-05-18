"""Outbound webhook delivery for marketplace apps.

Publishers register `WebhookEndpoint`s and the platform fires off
`WebhookDelivery` rows for declared topics. The dispatcher signs the payload
with the endpoint's HMAC secret, POSTs it, captures the response, and on
failure schedules a retry with exponential backoff.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import time
from datetime import timedelta

from django.db import transaction
from django.db.models import F
from django.utils import timezone

from apps.marketplace.models import (
    MarketplaceApp,
    WebhookDelivery,
    WebhookEndpoint,
)

# RFC-style exponential backoff, capped at ~6 hours.
_BACKOFF_SECONDS = [30, 120, 600, 1800, 7200, 21600]


def new_secret() -> str:
    return secrets.token_urlsafe(48)


def sign_payload(secret: str, body: bytes) -> str:
    return hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()


def _next_backoff_seconds(attempt_count: int) -> int:
    if attempt_count <= 0:
        return _BACKOFF_SECONDS[0]
    idx = min(attempt_count - 1, len(_BACKOFF_SECONDS) - 1)
    return _BACKOFF_SECONDS[idx]


@transaction.atomic
def enqueue_event(
    app: MarketplaceApp,
    *,
    topic: str,
    payload: dict,
    school=None,
    idempotency_key: str | None = None,
) -> list[WebhookDelivery]:
    """Enqueue a WebhookDelivery row for every active endpoint subscribed to topic."""

    endpoints = list(
        WebhookEndpoint.objects.filter(app=app, is_active=True)
        .select_for_update(skip_locked=True)
    )
    if idempotency_key is None:
        idempotency_key = secrets.token_urlsafe(24)
    rows = []
    for ep in endpoints:
        topics = list(ep.topics or [])
        if topics and topic not in topics and "*" not in topics:
            continue
        # Pre-sign so the wire signature is captured even before first attempt.
        body = json.dumps(payload, sort_keys=True).encode("utf-8")
        signature = sign_payload(ep.secret, body)
        row, created = WebhookDelivery.objects.get_or_create(
            endpoint=ep,
            idempotency_key=idempotency_key,
            defaults={
                "app": app,
                "school": school,
                "topic": topic,
                "payload": payload,
                "signature": signature,
                "status": WebhookDelivery.Status.PENDING,
                "next_attempt_at": timezone.now(),
            },
        )
        if created:
            rows.append(row)
    return rows


def deliver_once(delivery: WebhookDelivery, *, http_session=None) -> bool:
    """Attempt a single delivery. Returns True on 2xx success.

    `http_session` lets tests inject a stub; defaults to a `requests.Session`.
    """

    delivery.status = WebhookDelivery.Status.IN_FLIGHT
    delivery.attempt_count = F("attempt_count") + 1
    delivery.save(update_fields=["status", "attempt_count"])
    delivery.refresh_from_db(fields=["attempt_count"])

    started = time.monotonic()
    ok = False
    status_code = None
    snippet = ""
    error_message = ""

    try:
        if http_session is None:
            import requests  # type: ignore

            http_session = requests.Session()
        body = json.dumps(delivery.payload, sort_keys=True).encode("utf-8")
        resp = http_session.post(
            delivery.endpoint.url,
            data=body,
            headers={
                "Content-Type": "application/json",
                "X-RMC-Topic": delivery.topic,
                "X-RMC-Signature": delivery.signature,
                "X-RMC-Delivery-Id": str(delivery.pk),
                "X-RMC-Idempotency-Key": delivery.idempotency_key,
            },
            timeout=15,
        )
        status_code = getattr(resp, "status_code", None)
        try:
            snippet = (resp.text or "")[:1000]
        except Exception:
            snippet = ""
        ok = 200 <= (status_code or 0) < 300
    except Exception as exc:
        error_message = f"{type(exc).__name__}: {exc}"[:255]

    duration_ms = int((time.monotonic() - started) * 1000)
    now = timezone.now()
    if ok:
        delivery.status = WebhookDelivery.Status.SUCCEEDED
        delivery.completed_at = now
        delivery.response_status_code = status_code
        delivery.response_body_snippet = snippet
        delivery.duration_ms = duration_ms
        delivery.error_message = ""
        delivery.next_attempt_at = None
        delivery.save(
            update_fields=[
                "status",
                "completed_at",
                "response_status_code",
                "response_body_snippet",
                "duration_ms",
                "error_message",
                "next_attempt_at",
            ]
        )
        WebhookEndpoint.objects.filter(pk=delivery.endpoint_id).update(
            consecutive_failures=0,
            last_success_at=now,
        )
    else:
        next_status = (
            WebhookDelivery.Status.ABANDONED
            if delivery.attempt_count >= delivery.max_attempts
            else WebhookDelivery.Status.FAILED
        )
        delivery.status = next_status
        delivery.response_status_code = status_code
        delivery.response_body_snippet = snippet
        delivery.duration_ms = duration_ms
        delivery.error_message = error_message or (
            f"HTTP {status_code}" if status_code else "unknown"
        )
        if next_status == WebhookDelivery.Status.FAILED:
            delivery.next_attempt_at = now + timedelta(
                seconds=_next_backoff_seconds(delivery.attempt_count)
            )
        else:
            delivery.completed_at = now
            delivery.next_attempt_at = None
        delivery.save(
            update_fields=[
                "status",
                "response_status_code",
                "response_body_snippet",
                "duration_ms",
                "error_message",
                "next_attempt_at",
                "completed_at",
            ]
        )
        WebhookEndpoint.objects.filter(pk=delivery.endpoint_id).update(
            consecutive_failures=F("consecutive_failures") + 1,
            last_failure_at=now,
            last_failure_reason=delivery.error_message[:255],
        )
        # Auto-disable endpoints with 20+ consecutive failures.
        WebhookEndpoint.objects.filter(
            pk=delivery.endpoint_id, consecutive_failures__gte=20
        ).update(is_active=False)
    return ok


def deliver_due(*, limit: int = 50, http_session=None) -> int:
    """Deliver up to `limit` rows whose next_attempt_at is in the past.

    Returns the count of attempts made. Designed to be called from a Celery
    Beat scheduled task, but works as a manage.py command too.
    """

    now = timezone.now()
    qs = (
        WebhookDelivery.objects.filter(
            status__in=[
                WebhookDelivery.Status.PENDING,
                WebhookDelivery.Status.FAILED,
            ],
            next_attempt_at__lte=now,
        )
        .select_related("endpoint")
        .order_by("next_attempt_at")[:limit]
    )
    count = 0
    for row in qs:
        deliver_once(row, http_session=http_session)
        count += 1
    return count
