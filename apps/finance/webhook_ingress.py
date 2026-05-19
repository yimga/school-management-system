"""
Finance webhook ingress boundary (Shopify pillar).

Single module for provider callback dedupe and view delegation. App code outside
finance should import from here (or ``payment.webhook_ingress`` re-export), not
duplicate idempotency logic.
"""

from __future__ import annotations

from typing import Any

from django.http import HttpRequest, HttpResponse, JsonResponse

from apps.finance.webhooks.idempotency import (
    compute_idempotency_bucket,
    find_processed_duplicate,
)

__all__ = [
    "compute_idempotency_bucket",
    "duplicate_webhook_response",
    "find_processed_duplicate",
    "payment_provider_webhook_view",
    "resolve_webhook_dedup_bucket",
]


def resolve_webhook_dedup_bucket(
    provider: str,
    payload: dict[str, Any] | None,
    *,
    headers: dict[str, Any] | None = None,
    idempotency_header: str = "",
    reference_fallback: str = "",
) -> str:
    """Stable dedupe bucket: explicit header wins, then provider event id."""
    header = (idempotency_header or "").strip()
    if header:
        return f"idempotency:{header[:160]}"
    bucket = compute_idempotency_bucket(provider, payload, headers)
    if bucket:
        return bucket
    ref = (reference_fallback or "").strip()
    return ref


def duplicate_webhook_response() -> JsonResponse:
    """Canonical 200 ack for duplicate provider deliveries (stop retries)."""
    return JsonResponse({"status": "ignored", "reason": "duplicate"})


def payment_provider_webhook_view(
    request: HttpRequest, provider_slug: str
) -> HttpResponse:
    from apps.finance.views_payments import payment_provider_webhook

    return payment_provider_webhook(request, provider_slug)
