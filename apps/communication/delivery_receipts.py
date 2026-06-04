"""Delivery-receipt helper — upsert SMS/WhatsApp/push provider statuses.

Thin functional surface over
:class:`apps.communication.models_delivery_receipt.MessageDeliveryReceipt`.
Best-effort and NEVER raises into a webhook handler.
"""
from __future__ import annotations

import hashlib
import logging
from typing import Any

logger = logging.getLogger(__name__)

_RECIPIENT_HASH_LEN = 12

# Provider statuses that mean the message reached a final state.
_TERMINAL_STATUSES = frozenset(
    {
        "delivered", "failed", "undelivered", "read", "rejected",
        "expired", "deleted",
    }
)


def _hash_recipient(value: str) -> str:
    norm = (value or "").strip().lower()
    if not norm:
        return ""
    return hashlib.sha256(norm.encode("utf-8")).hexdigest()[:_RECIPIENT_HASH_LEN]


def record_delivery_receipt(
    *,
    channel: str,
    provider: str,
    provider_message_id: str,
    recipient: str = "",
    status: str = "",
    error_code: str = "",
    school: Any = None,
) -> bool:
    """Upsert a delivery receipt keyed by (channel, provider_message_id).

    A later status update for the same message id refreshes the same row
    (queued → sent → delivered). Returns True on success; never raises.
    """
    msg_id = (provider_message_id or "").strip()
    if not msg_id:
        return False
    status_l = (status or "").strip().lower()
    try:
        from apps.communication.models_delivery_receipt import MessageDeliveryReceipt

        defaults = {
            "provider": (provider or "")[:32],
            "status": status_l[:32],
            "error_code": (error_code or "")[:32],
            "terminal": status_l in _TERMINAL_STATUSES,
        }
        recipient_hash = _hash_recipient(recipient)
        if recipient_hash:
            defaults["recipient_hash"] = recipient_hash
        if school is not None and getattr(school, "pk", None):
            defaults["school"] = school
        # tenant-isolation-allow: delivery receipt keyed by provider message id, not tenant
        MessageDeliveryReceipt.objects.update_or_create(
            channel=(channel or "")[:12],
            provider_message_id=msg_id[:128],
            defaults=defaults,
        )
        logger.info(
            "communication.delivery_receipt.recorded channel=%s status=%s msg_id=%s",
            channel, status_l, msg_id,
        )
        return True
    except Exception as exc:  # broad-by-design — webhook never breaks on this
        logger.warning(
            "communication.delivery_receipt.record_failed err_type=%s",
            type(exc).__name__,
        )
        return False


__all__ = ["record_delivery_receipt"]
