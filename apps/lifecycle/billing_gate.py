"""Billing reconciliation gate for offboarding.

Question this answers: 'Is this tenant safe to hard-purge from a
financial perspective?'

Public API:
    check_billing_clearance(school) -> BillingClearance

If finance state is unresolvable (no billing app, no subscription
records, env doesn't have it wired), returns 'unknown' so operators
can override via dual-approval rather than blocking purges in dev.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class BillingClearance:
    cleared: bool
    reason: str
    outstanding_balance: Optional[Decimal]
    state: str  # "cleared" / "outstanding" / "unknown"


def _zero() -> Decimal:
    return Decimal("0")


def check_billing_clearance(school) -> BillingClearance:
    """Return a BillingClearance for the school's purge readiness.

    Conservative defaults: returns 'unknown' rather than 'cleared'
    when we can't reach billing data — operator must dual-approve.
    Never raises.
    """
    if not school or not getattr(school, "id", None):
        return BillingClearance(
            cleared=False,
            reason="unknown school",
            outstanding_balance=None,
            state="unknown",
        )
    try:
        from apps.billing.entitlements import limits

        # `limits` returns a dict; we ignore its actual shape and just
        # check for the existence of an outstanding-balance entry.
        # Specific billing helpers vary across the platform.
        snapshot = limits(school) or {}
        outstanding = snapshot.get("outstanding_balance")
        if outstanding is not None:
            try:
                amount = Decimal(str(outstanding))
            except (TypeError, ValueError):
                amount = _zero()
            if amount > _zero():
                return BillingClearance(
                    cleared=False,
                    reason=f"outstanding balance {amount}",
                    outstanding_balance=amount,
                    state="outstanding",
                )
            return BillingClearance(
                cleared=True,
                reason="zero balance",
                outstanding_balance=_zero(),
                state="cleared",
            )
    except Exception as exc:  # noqa: BLE001
        logger.info(
            "lifecycle.billing_gate.unreachable school_id=%s err=%s",
            school.id,
            type(exc).__name__,
        )
    return BillingClearance(
        cleared=False,
        reason="billing state unavailable — operator dual-approve required",
        outstanding_balance=None,
        state="unknown",
    )
