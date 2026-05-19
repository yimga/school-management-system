"""Atomic webhook idempotency claim (Shopify pillar — race-safe PSP ingress)."""

from __future__ import annotations

from typing import Literal

from django.db import IntegrityError, transaction
from django.db.models import Q

ClaimResult = Literal["claimed", "duplicate"]


@transaction.atomic
def claim_webhook_processing(
    *,
    provider: str,
    bucket: str,
    reference_id: str,
    client_ip: str,
    request_body_excerpt: str = "",
) -> tuple[ClaimResult, object | None]:
    """
    Claim a webhook bucket inside a DB transaction.

    Returns ``("claimed", log)`` for the first claimant or
    ``("duplicate", existing_log)`` when already processed or in flight.
    """
    if not bucket:
        return "claimed", None

    from apps.finance.models import WebhookLog

    terminal = (
        WebhookLog.Status.PROCESSED,
        WebhookLog.Status.DUPLICATE,
    )
    in_flight = (WebhookLog.Status.PROCESSING,)

    existing = (
        WebhookLog.objects.select_for_update()
        .filter(provider=provider)
        .filter(Q(idempotency_bucket=bucket) | Q(reference_id=bucket))
        .filter(
            status__in=(*terminal, *in_flight),
        )
        .order_by("-created_at")
        .first()
    )
    if existing is not None:
        return "duplicate", existing

    try:
        with transaction.atomic():
            log = WebhookLog.objects.create(
                provider=provider,
                reference_id=reference_id or bucket,
                idempotency_bucket=bucket,
                client_ip=client_ip or "0.0.0.0",
                signature_valid=True,
                status=WebhookLog.Status.PROCESSING,
                request_body=request_body_excerpt[:4000],
            )
    except IntegrityError:
        raced = (
            WebhookLog.objects.filter(provider=provider, idempotency_bucket=bucket)
            .order_by("-created_at")
            .first()
        )
        if raced is not None:
            return "duplicate", raced
        raise
    return "claimed", log


__all__ = ["claim_webhook_processing"]
