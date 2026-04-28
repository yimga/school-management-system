"""Resolve Stripe price IDs from plan codes (DB-backed; no view hardcoding)."""

from __future__ import annotations

from apps.billing.models import StripePlanPrice


def active_stripe_price_for_plan(
    plan_code: str, *, billing_cycle: str | None = None, currency: str | None = None
) -> StripePlanPrice | None:
    code = str(plan_code or "").strip()
    if not code:
        return None
    qs = StripePlanPrice.objects.filter(plan_code=code, is_active=True)
    if billing_cycle:
        qs = qs.filter(billing_cycle=str(billing_cycle).strip().upper())
    if currency:
        c = str(currency).strip().upper()
        if len(c) == 3:
            qs = qs.filter(currency=c)
    return qs.order_by("-updated_at").first()
