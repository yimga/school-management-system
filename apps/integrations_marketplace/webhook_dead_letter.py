"""v4.00.79 — WebhookDeadLetter persistence + sweep helpers.

When a webhook delivery exhausts its retry budget (see webhook_retry_fsm),
it gets parked here for operator-driven replay or auto-expiry.
"""
from __future__ import annotations
import base64
import logging
from datetime import timedelta

logger = logging.getLogger(__name__)

DEFAULT_EXPIRY_SECONDS = 7 * 24 * 60 * 60  # 7 days


def enqueue_dead_letter(*, provider: str, event_type: str, payload: bytes | str, reason: str = "", tenant_schema: str = "", attempt_count: int = 0, expires_in_seconds: int = DEFAULT_EXPIRY_SECONDS):
    """Park an exhausted webhook into the DLQ. Returns the row.
    Never raises — logs and returns None on DB failure (DLQ failure must not
    cascade and kill the worker loop)."""
    try:
        from django.utils import timezone as _tz
        from apps.integrations_marketplace.models import WebhookDeadLetter
        if isinstance(payload, str):
            payload_bytes = payload.encode("utf-8")
        else:
            payload_bytes = payload
        b64 = base64.b64encode(payload_bytes).decode("ascii")
        now = _tz.now()
        return WebhookDeadLetter.objects.create(
            provider=provider[:64],
            event_type=event_type[:128],
            payload_b64=b64,
            attempt_count=attempt_count,
            last_error_reason=(reason or "")[:256],
            tenant_schema=(tenant_schema or "")[:64],
            status="pending",
            created_at=now,
            expires_at=now + timedelta(seconds=expires_in_seconds) if expires_in_seconds > 0 else None,
        )
    except Exception as exc:  # noqa: BLE001
        logger.error("dlq enqueue failed: %s", exc)
        return None


def list_due(*, status: str = "pending", before=None, limit: int = 100):
    """Return up to `limit` rows matching `status` ordered oldest-first."""
    try:
        from apps.integrations_marketplace.models import WebhookDeadLetter
        qs = WebhookDeadLetter.objects.filter(status=status).order_by("created_at")
        if before is not None:
            qs = qs.filter(created_at__lte=before)
        return list(qs[:limit])
    except Exception as exc:  # noqa: BLE001
        logger.debug("dlq list_due failed: %s", exc)
        return []


def mark_replayed(dlq_id: int) -> bool:
    """Flip a row to status=replayed. Returns True on success."""
    try:
        from django.utils import timezone as _tz
        from apps.integrations_marketplace.models import WebhookDeadLetter
        n = WebhookDeadLetter.objects.filter(pk=dlq_id, status="pending").update(
            status="replayed", last_attempted_at=_tz.now(),
        )
        return n > 0
    except Exception as exc:  # noqa: BLE001
        logger.debug("dlq mark_replayed failed: %s", exc)
        return False


def sweep_expired_due(*, now=None) -> int:
    """Flip pending rows past their expires_at to status=expired. Returns count."""
    try:
        from django.utils import timezone as _tz
        from apps.integrations_marketplace.models import WebhookDeadLetter
        now = now or _tz.now()
        return WebhookDeadLetter.objects.filter(
            status="pending", expires_at__isnull=False, expires_at__lt=now,
        ).update(status="expired")
    except Exception as exc:  # noqa: BLE001
        logger.debug("dlq sweep_expired failed: %s", exc)
        return 0


def decode_payload(row) -> bytes:
    """Round-trip helper for the replay endpoint (Wave 12)."""
    return base64.b64decode(row.payload_b64.encode("ascii"))
