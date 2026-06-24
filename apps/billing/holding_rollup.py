"""Multi-currency rollup for holding companies (B4).

A holding company is a parent ``School`` with sub-schools. Each tenant is
single-currency, so a holding company cannot see a consolidated bill spanning
markets. This module aggregates a holding company's active sub-schools' billing
totals BY CURRENCY — with no FX conversion, so the result is a set of honest
per-currency buckets (USD 300, NGN 15000, …) rather than a faked single number.

``compute_holding_currency_totals`` is pure (no writes);
``materialize_holding_currency_rollups`` persists the result into
``HoldingCurrencyRollup`` rows (one per currency) and prunes stale buckets.

Source amount per sub-school is its computed subscription price
(``compute_subscription_price_for_school``), which yields both the total and the
currency. FLAT plans roll up fully; PER_STUDENT / TIERED sub-schools contribute
whatever their resolvable base is here (a live student count is not loaded
cross-tenant in this platform-level pass).
"""
from __future__ import annotations

import logging
from collections import defaultdict
from decimal import Decimal

logger = logging.getLogger(__name__)


def _as_decimal(value) -> Decimal | None:
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except (TypeError, ValueError):
        return None


def compute_holding_currency_totals(parent_school) -> dict:
    """Aggregate a holding company's active sub-schools' billing by currency.

    Pure — performs reads only. Returns ``{currency_code: {"total": Decimal,
    "count": int}}``. No FX conversion; each currency is its own bucket.
    Sub-schools with no plan or a non-positive total are skipped. Never raises.
    """
    totals: dict = {}
    if parent_school is None or not getattr(parent_school, "pk", None):
        return totals
    try:
        from apps.schools.models import School
    except (ImportError, RuntimeError):
        return totals
    try:
        from apps.billing.services import compute_subscription_price_for_school
    except (ImportError, RuntimeError):
        return totals
    try:
        # tenant-isolation-allow: holding-rollup-parent-school-hierarchy-platform-scope
        children = list(
            School.objects.filter(parent_school=parent_school, is_active=True)
        )
    except (AttributeError, RuntimeError, ValueError):
        return totals

    acc: dict = defaultdict(lambda: [Decimal("0.00"), 0])
    for child in children:
        plan = getattr(child, "plan", None)
        if plan is None:
            continue
        try:
            priced = compute_subscription_price_for_school(child, plan)
        except (AttributeError, RuntimeError, TypeError, ValueError):
            continue
        total = _as_decimal(priced.get("total"))
        if total is None or total <= 0:
            continue
        currency = (priced.get("currency_code") or "USD").upper()
        acc[currency][0] += total
        acc[currency][1] += 1

    for currency, (amount, count) in acc.items():
        totals[currency] = {"total": amount, "count": count}
    return totals


def materialize_holding_currency_rollups(parent_school) -> dict:
    """Compute and persist a holding company's per-currency rollup (B4).

    Upserts one ``HoldingCurrencyRollup`` row per currency and prunes currency
    rows that no longer have a contributor. Returns the computed totals. Never
    raises into a caller — logs and returns the computed totals on persistence
    trouble.
    """
    totals = compute_holding_currency_totals(parent_school)
    if parent_school is None or not getattr(parent_school, "pk", None):
        return totals
    try:
        from django.utils import timezone

        from apps.siteconfig.models_platform_catalog import HoldingCurrencyRollup
    except (ImportError, RuntimeError):
        return totals

    now = timezone.now()
    try:
        for currency, agg in totals.items():
            # tenant-isolation-allow: holding-rollup-keyed-by-parent-school-platform-scope
            HoldingCurrencyRollup.objects.update_or_create(
                parent_school=parent_school,
                currency_code=currency,
                defaults={
                    "total_amount": agg["total"],
                    "source_school_count": agg["count"],
                    "as_of": now,
                },
            )
        # Drop stale currency buckets that no longer have a contributor.
        # tenant-isolation-allow: holding-rollup-cleanup-scoped-to-parent-school
        HoldingCurrencyRollup.objects.filter(parent_school=parent_school).exclude(
            currency_code__in=list(totals.keys())
        ).delete()
    except (AttributeError, RuntimeError, ValueError) as exc:
        logger.warning(
            "billing.holding_rollup materialize failed school=%s: %s",
            getattr(parent_school, "pk", None),
            exc,
        )
    return totals


def iter_holding_parent_schools():
    """Active parent schools with at least one active child (platform scope)."""
    from django.db.models import Count, Q

    from apps.schools.models import School

    # tenant-isolation-allow: holding-rollup-parent-enumeration-platform-scope
    return School.objects.filter(is_active=True).annotate(
        active_child_count=Count(
            "child_schools",
            filter=Q(child_schools__is_active=True),
        )
    ).filter(active_child_count__gt=0)


def materialize_all_holding_currency_rollups() -> dict:
    """Refresh every holding company's per-currency buckets (beat entry)."""
    parents_refreshed = 0
    currency_buckets = 0
    for parent in iter_holding_parent_schools().iterator():
        totals = materialize_holding_currency_rollups(parent)
        parents_refreshed += 1
        currency_buckets += len(totals)
    return {
        "parents_refreshed": parents_refreshed,
        "currency_buckets": currency_buckets,
    }
