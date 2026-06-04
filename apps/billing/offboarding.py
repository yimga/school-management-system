"""Subscription cancellation for tenant offboarding.

Previously no offboarding/purge path cancelled a tenant's subscription. Because
``TenantSubscription`` is CASCADE-deleted with the School, the remote (Stripe)
subscription kept billing with NO local trace once the row was gone. This module
initiates cancellation BEFORE the purge and records the external reference into
the purge manifest so the remote cancellation is reconcilable afterward.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def _try_remote_cancel(external_ref: str) -> bool:
    """Attempt a provider-side subscription cancel. Returns True when cancelled.

    No live Stripe cancel client is wired yet (the provider API is an external
    dependency). This is the seam where ``stripe.Subscription.delete(ref)`` plugs
    in. Until then it returns False so the ref is recorded as ``remote_pending``
    for operator/cron reconciliation rather than silently assumed cancelled.
    """
    if not external_ref:
        return False
    # EXTERNAL: wire the provider cancel here once billing credentials exist.
    return False


def cancel_subscriptions_for_offboarding(school) -> dict:
    """Cancel a tenant's platform subscriptions at offboarding (best-effort).

    Marks local ``TenantSubscription`` rows CANCELED (status + canceled_at) and
    captures each ``external_subscription_ref`` so remote cancellation survives
    the subsequent CASCADE delete. Never raises — cleanup must not fail a purge.
    """
    result: dict = {
        "canceled": 0,
        "external_refs": [],
        "remote_canceled": 0,
        "remote_pending": [],
    }
    try:
        from django.utils import timezone

        from apps.billing.models import TenantSubscription

        now = timezone.now()
        subs = list(
            TenantSubscription.objects.filter(  # tenant-isolation-allow: explicit-school-scoped-subscription-cancellation-on-offboarding
                school_id=school.pk,
            ).exclude(status=TenantSubscription.Status.CANCELED)
        )
        for sub in subs:
            ref = (sub.external_subscription_ref or "").strip()
            if ref:
                result["external_refs"].append(ref)
                if _try_remote_cancel(ref):
                    result["remote_canceled"] += 1
                else:
                    result["remote_pending"].append(ref)
            sub.status = TenantSubscription.Status.CANCELED
            sub.canceled_at = now
            sub.save(update_fields=["status", "canceled_at"])
            result["canceled"] += 1
    except Exception as exc:  # noqa: BLE001 - cleanup must never fail offboarding
        logger.warning(
            "billing.cancel_subscriptions_for_offboarding failed school=%s: %s",
            getattr(school, "pk", None),
            exc,
        )
        result["error"] = str(exc)[:200]
    if result["remote_pending"]:
        logger.warning(
            "billing.offboarding remote subscription cancel PENDING school=%s refs=%s "
            "(no provider cancel client wired — reconcile manually)",
            getattr(school, "pk", None),
            result["remote_pending"],
        )
    return result
