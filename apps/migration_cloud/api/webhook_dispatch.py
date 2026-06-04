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
ciphertext bytes.

Header families (v3.35.0 dual-emit window):

  * New canonical family — matches the packaged SDKs
    (``runmycampus-webhook-verifier`` PyPI / ``@runmycampus/webhook-verifier``
    npm):
        ``X-RunMyCampus-Signature: sha256=<hex>``
        ``X-RunMyCampus-Timestamp: <unix-seconds>``
        ``X-RunMyCampus-Version: v1``
        ``X-RunMyCampus-Event: <event_type>``
        ``X-RunMyCampus-Delivery: <delivery_id>``
  * Legacy family (emitted in parallel until 2026-08-18 — see
    :data:`LEGACY_HEADER_DEPRECATION_DATE`):
        ``X-Migration-Cloud-Signature: sha256=<hex>`` (byte-identical)
        ``X-Migration-Cloud-Timestamp: <unix-seconds>`` (byte-identical)
        ``X-Migration-Cloud-Version: v1``
        ``X-Migration-Cloud-Event: <event_type>``
        ``X-Migration-Cloud-Delivery: <delivery_id>``

Operators can opt-out of legacy emission early by setting
``RMC_EMIT_LEGACY_WEBHOOK_HEADERS=0`` (Django setting
``MIGRATION_CLOUD_EMIT_LEGACY_HEADERS``). Default is ON for
backwards-compat. The new family is ALWAYS emitted.

Both signatures are computed identically over the same canonical body —
swapping header names doesn't change the bytes a customer compares.

Receivers verify with the secret they were given **once** at subscription
creation (the platform also stores ``secret_hash`` for support workflows).

Production note: log lines NEVER include the payload body or the secret.
Only IDs, sizes, status codes, and event types.

See ``docs/WEBHOOK_HEADER_MIGRATION_2026.md`` for the customer-facing
migration timeline.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
from datetime import date
from datetime import timedelta

from django.conf import settings
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

#: v3.35.0 — sliding window for the idempotency-key collision guard.
#: Two ``enqueue`` calls with the same ``(subscription_id,
#: idempotency_key)`` within this window collapse to a single delivery
#: row (the second call returns the existing row + logs a warning).
IDEMPOTENCY_WINDOW = timedelta(hours=24)

# v3.35.0 — header family migration window.
#
# The legacy ``X-Migration-Cloud-*`` header family is co-emitted alongside
# the new canonical ``X-RunMyCampus-*`` family during a 90-day deprecation
# window. After ``LEGACY_HEADER_DEPRECATION_DATE`` the legacy family will
# be removed in v3.40.0 (or the earliest release on/after that date).
# Customers receive a ``X-RunMyCampus-Header-Deprecation`` header on every
# delivery during the window pointing at this date.
LEGACY_HEADER_DEPRECATION_DATE = "2026-08-18"
LEGACY_HEADER_DEPRECATION_NOTICE = (
    f"legacy-x-migration-cloud-headers-will-be-removed-after-"
    f"{LEGACY_HEADER_DEPRECATION_DATE}"
)
SIGNATURE_FORMAT_VERSION = "v1"


def _legacy_header_deprecation_cutover_date() -> date:
    """Return the configured legacy-header removal date."""
    raw = getattr(
        settings,
        "MIGRATION_CLOUD_LEGACY_HEADER_DEPRECATION_DATE",
        LEGACY_HEADER_DEPRECATION_DATE,
    )
    try:
        return date.fromisoformat(str(raw))
    except ValueError:
        logger.warning(
            "migration_cloud_webhook_bad_legacy_header_cutover_date value=%s",
            raw,
        )
        return date.fromisoformat(LEGACY_HEADER_DEPRECATION_DATE)


def _legacy_header_window_active() -> bool:
    """Return True through the announced legacy-header migration window."""
    return timezone.localdate() <= _legacy_header_deprecation_cutover_date()


def _emit_legacy_headers_enabled() -> bool:
    """Return True iff the dispatcher should emit the legacy header family.

    Backwards-compat default: ON. Operators can flip the env var
    ``RMC_EMIT_LEGACY_WEBHOOK_HEADERS=0`` (or set
    ``settings.MIGRATION_CLOUD_EMIT_LEGACY_HEADERS = False``) once their
    receivers have migrated to the new ``X-RunMyCampus-*`` family. After
    the announced cutover date the legacy family is suppressed even if
    the compatibility setting is still true.
    """
    return bool(
        getattr(settings, "MIGRATION_CLOUD_EMIT_LEGACY_HEADERS", True)
    ) and _legacy_header_window_active()


def _event_class_matches(subscription, event_type: str) -> bool:
    """Return True iff ``event_type`` matches one of ``subscription.event_classes``.

    Each entry is a coarse ``"<class>.*"`` glob. Default is ``["migration.*"]``
    for legacy v3.32 subscriptions that never set the column. Empty list
    after explicit clear is also treated as the default (defensive).
    """
    classes = list(getattr(subscription, "event_classes", None) or [])
    if not classes:
        classes = ["migration.*"]
    head = (event_type or "").split(".", 1)[0]
    for glob in classes:
        if not isinstance(glob, str):
            continue
        if glob == "*":
            return True
        # Accept literal class prefix (``"<head>.*"``) or exact match.
        if glob == event_type:
            return True
        if glob.endswith(".*") and glob[:-2] == head:
            return True
    return False


def _canonical_payload_bytes(payload: dict) -> bytes:
    """Return the canonical byte form used for HMAC signing.

    Keys sorted, no whitespace, UTF-8 — matches what receivers compute.
    """
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _sign(secret_bytes: bytes, payload_bytes: bytes) -> str:
    """Return ``sha256=<hex>`` HMAC for the signature header.

    The same digest is emitted under BOTH ``X-RunMyCampus-Signature`` and
    ``X-Migration-Cloud-Signature`` headers — they are byte-identical
    aliases during the v3.35.0 dual-emit window.
    """
    digest = hmac.new(secret_bytes, payload_bytes, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def _build_outbound_headers(
    *,
    signature: str,
    event_type: str,
    delivery_id,
    timestamp: str,
    emit_legacy: bool,
) -> dict:
    """Build the outbound HTTP header dict for one delivery.

    Always emits the new ``X-RunMyCampus-*`` family. Emits the
    deprecation notice header only during the migration window. Co-emits
    the legacy ``X-Migration-Cloud-*`` family iff ``emit_legacy`` is True.
    """
    headers = {
        "Content-Type": "application/json",
        # New canonical family — matches packaged SDKs.
        "X-RunMyCampus-Signature": signature,
        "X-RunMyCampus-Timestamp": timestamp,
        "X-RunMyCampus-Version": SIGNATURE_FORMAT_VERSION,
        "X-RunMyCampus-Event": event_type,
        "X-RunMyCampus-Delivery": str(delivery_id),
        "User-Agent": "RunMyCampus-MigrationCloud/3.35",
    }
    if _legacy_header_window_active():
        headers["X-RunMyCampus-Header-Deprecation"] = (
            LEGACY_HEADER_DEPRECATION_NOTICE
        )
    if emit_legacy and _legacy_header_window_active():
        # Legacy family — byte-identical signature, will be removed
        # after LEGACY_HEADER_DEPRECATION_DATE.
        headers["X-Migration-Cloud-Signature"] = signature
        headers["X-Migration-Cloud-Timestamp"] = timestamp
        headers["X-Migration-Cloud-Version"] = SIGNATURE_FORMAT_VERSION
        headers["X-Migration-Cloud-Event"] = event_type
        headers["X-Migration-Cloud-Delivery"] = str(delivery_id)
    return headers


def _get_header_case_insensitive(headers, name: str):
    """Return a header value from mappings that are not case-normalized."""
    for candidate in (name, name.lower(), name.upper()):
        value = headers.get(candidate)
        if value:
            return value
    target = name.lower()
    try:
        items = headers.items()
    except AttributeError:
        return None
    for key, value in items:
        if isinstance(key, str) and key.lower() == target and value:
            return value
    return None


def parse_inbound_signature_header(
    headers,
) -> tuple[str | None, str | None]:
    """Return ``(signature, source_family)`` from an inbound headers map.

    Accepts both the new and legacy header families during the deprecation
    window. The new ``X-RunMyCampus-Signature`` is preferred when both are
    present (matches the SDK contract).

    Args:
        headers: Anything with a ``get(name, default)`` accessor — Django
            ``HttpRequest.headers``, ``requests.Response.headers``,
            ``dict``, etc.

    Returns:
        ``(value, "new")`` if the new header is present;
        ``(value, "legacy")`` if only the legacy header is present;
        ``(None, None)`` otherwise.
    """
    if headers is None:
        return None, None
    try:
        new_value = _get_header_case_insensitive(
            headers,
            "X-RunMyCampus-Signature",
        )
    except AttributeError:
        return None, None
    if new_value:
        return new_value, "new"
    legacy_value = _get_header_case_insensitive(
        headers,
        "X-Migration-Cloud-Signature",
    )
    if legacy_value:
        return legacy_value, "legacy"
    return None, None


def _find_existing_idempotent_delivery(subscription, idempotency_key: str):
    """Return an existing delivery row that should short-circuit a new enqueue.

    Looks for a row with the same ``(subscription_id, idempotency_key)``
    created within :data:`IDEMPOTENCY_WINDOW` whose status is in
    ``{pending, delivered}``. ``failed`` / ``exhausted`` rows do NOT
    short-circuit — those represent a final outcome and the caller is
    allowed to retry with the same key after the window or via the
    operator replay path.

    Returns ``None`` if no collision; the live delivery row otherwise.
    Empty ``idempotency_key`` disables the guard entirely (legacy
    enqueue sites that don't pass one keep working unchanged).
    """
    if not idempotency_key:
        return None
    from apps.migration_cloud.models import (
        MigrationCloudWebhookDelivery,
        WebhookDeliveryStatus,
    )

    window_start = timezone.now() - IDEMPOTENCY_WINDOW
    # tenant-isolation-allow: idempotency-key-scoped-by-subscription
    return (
        MigrationCloudWebhookDelivery.objects.filter(
            subscription_id=subscription.pk,
            idempotency_key=idempotency_key,
            created_at__gte=window_start,
            status__in=[
                WebhookDeliveryStatus.PENDING,
                WebhookDeliveryStatus.DELIVERED,
            ],
        )
        .order_by("-created_at")
        .first()
    )


def enqueue(
    subscription,
    event_type: str,
    payload: dict,
    *,
    idempotency_key: str = "",
):
    """Create a pending ``MigrationCloudWebhookDelivery`` row.

    The dispatcher Celery task picks it up on the next tick. We pre-compute
    the signature here so receivers can verify even on the very first
    attempt (the secret may be wrapped/rotated before retry).

    v3.35.0 — when the caller supplies ``idempotency_key`` and a row
    with the same ``(subscription_id, idempotency_key)`` already exists
    within :data:`IDEMPOTENCY_WINDOW` with status in
    ``{pending, delivered}``, we DO NOT create a duplicate row — we log
    a warning and return the existing row. This prevents producer-side
    double-fires from doubling outbound HTTP traffic to subscribers.
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
    # v3.35.0 — idempotency-key collision guard (runs BEFORE the
    # event-class / event-types filters; a duplicate is a duplicate even
    # if it would have been filtered out for the second call).
    existing = _find_existing_idempotent_delivery(subscription, idempotency_key)
    if existing is not None:
        logger.warning(
            "migration_cloud_webhook_idempotency_collision "
            "sub_id=%s existing_delivery_id=%s event=%s",
            subscription.pk, existing.pk, event_type,
        )
        return existing
    # v3.33.0 — event-class opt-in gate. Coarse glob: e.g. a
    # ``"schoolops.meal_plan.low_balance_triggered"`` event matches only
    # subscriptions whose ``event_classes`` list contains
    # ``"schoolops.*"``. Empty / missing list defaults to ``"migration.*"``
    # for backwards compatibility with v3.32 subscriptions.
    if not _event_class_matches(subscription, event_type):
        logger.info(
            "migration_cloud_webhook_skip_event_class sub_id=%s event=%s",
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
        idempotency_key=idempotency_key or "",
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
    # Unix-seconds timestamp lets receivers use the SDK's clock-skew
    # check (default 300s window). We compute this at attempt time so
    # retries get a fresh timestamp — receivers anchored to ``now``
    # don't have to special-case 24h-old retries.
    timestamp = str(int(timezone.now().timestamp()))
    headers = _build_outbound_headers(
        signature=row.request_signature,
        event_type=row.event_type,
        delivery_id=row.pk,
        timestamp=timestamp,
        emit_legacy=_emit_legacy_headers_enabled(),
    )

    row.attempt_count += 1
    status_code = 0
    err = ""
    # SSRF guard at DELIVERY time too (not just registration) so a subscription
    # whose DNS now points at an internal address can't be used to beacon
    # internally. On block we fall through to the normal failure/retry/exhaust
    # path (no HTTP call made) rather than delivering.
    from apps.security.ssrf import is_safe_public_url

    _safe, _reason = is_safe_public_url(sub.url, allow_http=False)
    if not _safe:
        logger.warning(
            "migration_cloud_webhook_blocked_unsafe_target sub_id=%s reason=%s",
            sub.pk, _reason,
        )
        err = "blocked_unsafe_target"
    try:
        if not _safe:
            raise RuntimeError("blocked_unsafe_target")
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
    except Exception as exc:  # network failure of any kind (incl. blocked target)
        err = err or type(exc).__name__
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
            # v4.00.79 — park exhausted delivery in WebhookDeadLetter for
            # operator-driven replay (helper is defensive; DLQ failure
            # never breaks the delivery loop).
            try:
                from apps.integrations_marketplace import webhook_dead_letter as _dlq
                _dlq.enqueue_dead_letter(
                    provider="migration_cloud",
                    event_type=row.event_type,
                    payload=payload_bytes,
                    reason=err or f"http_{status_code}",
                    tenant_schema=getattr(getattr(sub, "tenant", None), "schema_name", ""),
                    attempt_count=row.attempt_count,
                )
            except Exception as _dlq_exc:  # noqa: BLE001
                logger.warning(
                    "migration_cloud_webhook_dlq_enqueue_failed sub_id=%s delivery_id=%s exc=%s",
                    sub.pk, row.pk, _dlq_exc,
                )
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
    # v3.38.0 — operational metric (best-effort; never breaks delivery).
    try:
        from apps.migration_cloud import metrics as _mc_metrics
        _mc_metrics.record_webhook_delivery(
            subscription_id=sub.pk,
            status=row.status,
            http_status=status_code,
        )
    except Exception as _metric_exc:  # noqa: BLE001
        logger.warning(
            "migration_cloud_webhook_delivery_metric_failed err=%s",
            type(_metric_exc).__name__,
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
