"""
Part F Section 25.1: Proration for subscription billing — compute prorated amount for partial period.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal


def compute_proration(
    period_start: date,
    period_end: date,
    amount: Decimal,
    *,
    effective_from: date | None = None,
    effective_to: date | None = None,
) -> Decimal:
    """
    Prorate amount for a partial billing period (Part F 25.1).
    If effective_from/effective_to are given, prorate for that sub-interval within [period_start, period_end].
    Otherwise returns amount (full period).
    """
    total_days = max((period_end - period_start).days + 1, 1)
    if effective_from is None and effective_to is None:
        return amount
    start = effective_from or period_start
    end = effective_to or period_end
    if start > end:
        return Decimal("0")
    # Clamp to period
    start = max(start, period_start)
    end = min(end, period_end)
    days = max((end - start).days + 1, 1)
    return (amount * Decimal(days) / Decimal(total_days)).quantize(Decimal("0.01"))
