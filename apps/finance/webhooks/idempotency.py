"""Webhook idempotency: short-circuit duplicate deliveries before invoking handlers.

Reuses the existing `apps.finance.models.WebhookLog.idempotency_bucket` index.
The contract:

    bucket = compute_idempotency_bucket(provider, payload, headers)
    duplicate = find_processed_duplicate(provider, bucket)
    if duplicate is not None:
        return cached_response(duplicate)
    log = create_received(provider, bucket, request, body)
    try:
        ...handle...
        mark_processed(log)
    except Exception:
        mark_failed(log, error_message)

Per-provider event-id extraction so two webhooks with the same provider
event id never run the side-effect twice, even on retry.
"""

from __future__ import annotations

from typing import Any


def _first_str(*candidates: Any) -> str:
    for c in candidates:
        if c is None:
            continue
        s = str(c).strip()
        if s:
            return s
    return ""


def _stripe_event_id(payload: dict[str, Any]) -> str:
    return _first_str(payload.get("id"))


def _paystack_event_id(payload: dict[str, Any]) -> str:
    data = payload.get("data") if isinstance(payload, dict) else None
    if isinstance(data, dict):
        return _first_str(
            data.get("id"),
            data.get("reference"),
            payload.get("id"),
        )
    return _first_str(payload.get("id"), payload.get("reference"))


def _flutterwave_event_id(payload: dict[str, Any]) -> str:
    data = payload.get("data") if isinstance(payload, dict) else None
    if isinstance(data, dict):
        return _first_str(
            data.get("id"),
            data.get("tx_ref"),
            data.get("flw_ref"),
            payload.get("id"),
        )
    return _first_str(payload.get("id"), payload.get("tx_ref"))


def _aggregator_event_id(payload: dict[str, Any]) -> str:
    return _first_str(
        payload.get("transaction_id"),
        payload.get("reference"),
        payload.get("external_reference"),
        payload.get("id"),
    )


_EXTRACTORS = {
    "stripe": _stripe_event_id,
    "paystack": _paystack_event_id,
    "flutterwave": _flutterwave_event_id,
    "mtn_momo": _aggregator_event_id,
    "mtn": _aggregator_event_id,
    "orange_money": _aggregator_event_id,
    "orange_momo": _aggregator_event_id,
    "orange": _aggregator_event_id,
}


def compute_idempotency_bucket(
    provider: str,
    payload: dict[str, Any] | None,
    headers: dict[str, Any] | None = None,
) -> str:
    """Return a stable bucket key for dedup, or empty string when ungeddable."""
    p = (provider or "").strip().lower()
    payload = payload if isinstance(payload, dict) else {}
    headers = headers or {}
    # An explicit Idempotency-Key header (RFC draft) wins when present.
    for h in ("Idempotency-Key", "X-Idempotency-Key"):
        for k, v in headers.items():
            if str(k).strip().lower() == h.lower():
                val = str(v or "").strip()
                if val:
                    return f"idempotency:{val}"
    extract = _EXTRACTORS.get(p)
    event_id = extract(payload) if extract else _aggregator_event_id(payload)
    return f"{p}:{event_id}" if event_id else ""


def find_processed_duplicate(provider: str, bucket: str):
    """Return the existing PROCESSED WebhookLog for (provider, bucket) or None.

    Imports are local so this module stays import-safe outside Django context.
    """
    if not bucket:
        return None
    from apps.finance.models import WebhookLog  # local import — Django boundary

    from django.db.models import Q

    return (
        WebhookLog.objects.filter(
            provider=provider,
            status__in=(
                WebhookLog.Status.PROCESSED,
                WebhookLog.Status.DUPLICATE,
            ),
        )
        .filter(Q(idempotency_bucket=bucket) | Q(reference_id=bucket))
        .order_by("-created_at")
        .first()
    )


__all__ = [
    "compute_idempotency_bucket",
    "find_processed_duplicate",
]
