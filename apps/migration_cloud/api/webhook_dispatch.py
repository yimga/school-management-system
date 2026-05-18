"""Outbound webhook dispatcher for the Migration Cloud REST API (v3.29).

Two public callables:

  * :func:`enqueue` — record a delivery row for a (subscription, event_type,
    payload) triple. Called inline from bundle-lifecycle actions in
    :mod:`apps.migration_cloud.api.viewsets`.
  * :func:`deliver_due` — Celery task processing rows whose
    ``next_retry_at <= now`` (or freshly created with no retry time).

Retry schedule (per task brief):
    attempt 1 → 1m, 2 → 5m, 3 → 30m, 4 → 2h, 5 → 12h, 6 → 24h → ``exhausted``.

HMAC: outbound deliveries sign ``payload_json`` (sorted-keys, separators
``(",", ":")``) with the subscription's secret material — stored in
``secret_ciphertext`` and Fernet-encrypted at rest by
:class:`apps.accounts.legacy_hashes.encryption.EncryptedBinaryField`
(v3.32.0). Reads transparently decrypt; the dispatcher never touches
ciphertext bytes. Header:
    ``X-Migration-Cloud-Signature: sha256=<hex>``
plus
    ``X-Migration-Cloud-Event: <event_type>``
    ``X-Migration-Cloud-Delivery: <delivery_id>``.

Receivers verify with the secret they were given **once** at subscription
creation (the platform also stores ``secret_hash`` for support workflows).

Production note: log lines NEVER include the payload body or the secret.
Only IDs, sizes, status codes, and event types.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
from datetime import timedelta

from django.utils import timezone

try:  # pragma: no cover — Celery is the prod path; tests run sans worker.
    from celery import shared_task
except ImportError:  # pragma: no cover — defensive
    def shared_task(*args, **kwargs):  # type: ignore[no-redef]
        def _decorator(fn):
            return fn
        if args and callable(args[0]) and not kwargs:
            return args[0]
        return _decorator

logger = logging.getLogger(__name__)


# Retry schedule expressed as timedelta backoffs per attempt index (0-based).
RETRY_SCHEDULE = [
    timedelta(minutes=1),
    timedelta(minutes=5),
    timedelta(minutes=30),
    timedelta(hours=2),
    timedelta(hours=12),
    timedelta(hours=24),
]
MAX_ATTEMPTS = len(RETRY_SCHEDULE)


def _canonical_payload_bytes(payload: dict) -> bytes:
    """Return the canonical byte form used for HMAC signing.

    Keys sorted, no whitespace, UTF-8 — matches what receivers compute.
    """
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _sign(secret_bytes: bytes, payload_bytes: bytes) -> str:
    """Return ``sha256=<hex>`` HMAC for the X-Migration-Cloud-Signature header."""
    digest = hmac.new(secret_bytes, payload_bytes, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def enqueue(subscription, event_type: str, payload: dict):
    """Create a pending ``MigrationCloudWebhookDelivery`` row.

    The dispatcher Celery task picks it up on the next tick. We pre-compute
    the signature here so receivers can verify even on the very first
    attempt (the secret may be wrapped/rotated before retry).
    """
    # Local import — keeps Celery/Django app-load order safe.
    from apps.migration_cloud.models import (
        MigrationCloudWebhookDelivery,
        WebhookDeliveryStatus,
    )

    if not subscription.active:
        logger.info(
            "migration_cloud_webhook_skip_inactive sub_id=%s event=%s",
            subscription.pk, event_type,
        )
        return None
    if subscription.event_types and event_type not in subscription.event_types:
        logger.info(
            "migration_cloud_webhook_skip_event_filter sub_id=%s event=%s",
            subscription.pk, event_type,
        )
        return None

    payload_bytes = _canonical_payload_bytes(payload)
    secret_bytes = bytes(subscription.secret_ciphertext or b"")
    signature = _sign(secret_bytes, payload_bytes) if secret_bytes else ""

    row = MigrationCloudWebhookDelivery.objects.create(
        subscription=subscription,
        event_type=event_type,
        payload_json=payload,
        request_signature=signature,
        attempt_count=0,
        status=WebhookDeliveryStatus.PENDING,
        next_retry_at=timezone.now(),  # eligible immediately
    )
    logger.info(
        "migration_cloud_webhook_enqueued sub_id=%s delivery_id=%s event=%s bytes=%s",
        subscription.pk, row.pk, event_type, len(payload_bytes),
    )
    return row


def _deliver_one(row) -> bool:
    """Attempt to POST one delivery row. Return True on 2xx, False otherwise.

    Updates the row in-place with status / next_retry_at / counts. Network
    layer uses ``requests`` if available; falls back to ``urllib`` so the
    dispatcher works in environments without ``requests`` installed.
    """
    from apps.migration_cloud.models import WebhookDeliveryStatus

    sub = row.subscription
    payload_bytes = _canonical_payload_bytes(row.payload_json)
    headers = {
        "Content-Type": "application/json",
        "X-Migration-Cloud-Signature": row.request_signature,
        "X-Migration-Cloud-Event": row.event_type,
        "X-Migration-Cloud-Delivery": str(row.pk),
        "User-Agent": "RunMyCampus-MigrationCloud/3.29",
    }

    row.attempt_count += 1
    status_code = 0
    err = ""
    try:
        try:
            import requests  # type: ignore

            response = requests.post(
                sub.url, data=payload_bytes, headers=headers, timeout=15,
            )
            status_code = int(response.status_code)
        except ImportError:
            # urllib fallback — keeps dispatcher importable in lean envs.
            from urllib import error as _urlerr
            from urllib import request as _urlreq

            req = _urlreq.Request(
                sub.url, data=payload_bytes, headers=headers, method="POST",
            )
            try:
                with _urlreq.urlopen(req, timeout=15) as resp:
                    status_code = int(resp.status)
            except _urlerr.HTTPError as http_err:
                status_code = int(http_err.code)
                err = f"HTTP {http_err.code}"
    except Exception as exc:  # network failure of any kind
        err = type(exc).__name__
        logger.exception(
            "migration_cloud_webhook_deliver_exception sub_id=%s delivery_id=%s",
            sub.pk, row.pk,
        )

    row.last_response_code = status_code or None
    row.last_error = err[:1000]

    succeeded = 200 <= status_code < 300
    if succeeded:
        row.status = WebhookDeliveryStatus.DELIVERED
        row.delivered_at = timezone.now()
        row.next_retry_at = None
        sub.last_delivery_status = "delivered"
    else:
        if row.attempt_count >= MAX_ATTEMPTS:
            row.status = WebhookDeliveryStatus.EXHAUSTED
            row.next_retry_at = None
            sub.last_delivery_status = "exhausted"
        else:
            row.status = WebhookDeliveryStatus.PENDING
            row.next_retry_at = timezone.now() + RETRY_SCHEDULE[row.attempt_count - 1]
            sub.last_delivery_status = "failed"

    row.save(update_fields=[
        "attempt_count", "status", "next_retry_at",
        "last_response_code", "last_error", "delivered_at",
    ])
    sub.save(update_fields=["last_delivery_status"])
    logger.info(
        "migration_cloud_webhook_delivered sub_id=%s delivery_id=%s "
        "attempt=%s status=%s response_code=%s",
        sub.pk, row.pk, row.attempt_count, row.status, status_code,
    )
    return succeeded


def deliver_due(batch_size: int = 200) -> dict:
    """Process up to ``batch_size`` deliveries whose retry window has arrived.

    Celery wires this on a periodic schedule (every 30s recommended).
    Returns a dict summary for visibility in worker logs.

    v3.32.0 — per-tenant quota integration: before attempting a delivery
    we ask :class:`TenantRateLimiter` whether the tenant has bucket
    space; if not, we *defer* the row (status stays ``pending``,
    ``deferred_until`` set to the next hour boundary, attempt_count is
    NOT bumped). This protects a tenant's retry budget from being burned
    by their own runaway emitter.
    """
    from apps.migration_cloud.api.rate_limiting import (
        _next_hour_boundary,
        default_tenant_rate_limiter,
    )
    from apps.migration_cloud.models import (
        MigrationCloudWebhookDelivery,
        WebhookDeliveryStatus,
    )

    now = timezone.now()
    # tenant-isolation-allow: webhook-delivery-scheduler-cross-tenant-by-design-each-row-targets-one-tenant
    due_qs = MigrationCloudWebhookDelivery.objects.filter(
        status=WebhookDeliveryStatus.PENDING,
        next_retry_at__lte=now,
    ).select_related("subscription")[:batch_size]

    processed = 0
    delivered = 0
    deferred = 0
    for row in due_qs:
        # Quota check — skip-not-fail if the tenant bucket is exhausted.
        tenant_id = getattr(row.subscription, "tenant_id", None)
        if tenant_id is not None:
            decision = default_tenant_rate_limiter.try_consume(tenant_id)
            if not decision.allowed:
                row.deferred_until = _next_hour_boundary(now)
                row.deferred_reason = decision.reason
                row.next_retry_at = row.deferred_until
                # Row stays PENDING; attempt_count NOT incremented.
                row.save(update_fields=[
                    "deferred_until", "deferred_reason", "next_retry_at",
                ])
                deferred += 1
                logger.info(
                    "migration_cloud_webhook_deferred "
                    "delivery_id=%s tenant_id=%s reason=%s "
                    "next_retry_at=%s",
                    row.pk, tenant_id, decision.reason,
                    row.next_retry_at.isoformat() if row.next_retry_at else "",
                )
                continue
            if decision.is_soft_warn:
                # Annotate the row but still deliver. Operator UI can
                # surface this via the delivery log.
                row.deferred_reason = decision.reason
        processed += 1
        if _deliver_one(row):
            delivered += 1
    summary = {
        "processed": processed,
        "delivered": delivered,
        "deferred": deferred,
        "ts": now.isoformat(),
    }
    logger.info("migration_cloud_webhook_dispatch_run %s", summary)
    return summary


# ─── Celery task wrapper ───────────────────────────────────────────────────


@shared_task(name="apps.migration_cloud.api.webhook_dispatch.deliver_due_task")
def deliver_due_task(batch_size: int = 200) -> dict:
    """Celery beat entry point: thin wrapper around :func:`deliver_due`.

    Kept separate so unit tests can call ``deliver_due()`` directly
    without dragging the Celery decorator's wrapping behavior in.
    """
    return deliver_due(batch_size=batch_size)
