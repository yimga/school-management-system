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
from decimal import Decimal, InvalidOperation
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


def _as_decimal(value) -> Decimal:
    try:
        return Decimal(str(value or 0))
    except (TypeError, ValueError, InvalidOperation):
        return _zero()


def _platform_debt(school) -> Optional[Decimal]:
    """What the tenant still owes the PLATFORM (issued, unpaid platform invoices).

    Returns ``None`` — not zero — when the billing ledger is unreachable, so the
    caller can tell 'nothing owed' apart from 'could not look'.
    """
    try:
        from django.db.models import Sum

        from apps.billing.models import PlatformInvoice

        total = PlatformInvoice.objects.filter(
            school=school, status=PlatformInvoice.Status.ISSUED
        ).aggregate(total=Sum("total"))["total"]
    except Exception as exc:  # noqa: BLE001 — gate never raises
        logger.info(
            "lifecycle.billing_gate.platform_unreachable school_id=%s err=%s",
            school.id,
            type(exc).__name__,
        )
        return None
    return _as_decimal(total)


def _tenant_ledger_outstanding(school) -> Optional[Decimal]:
    """Unsettled money on the tenant's OWN ledger, which a purge would destroy.

    Draft invoices are not owed by anyone yet and void/soft-deleted rows are not
    money, so both are excluded. Returns ``None`` when finance is unreachable.
    """
    try:
        from django.db.models import Sum

        from apps.finance.models import Invoice

        total = (
            Invoice.objects.filter(
                school=school, deleted_at__isnull=True, balance_amount__gt=0
            )
            .exclude(status__in=[Invoice.Status.VOID, Invoice.Status.DRAFT])
            .aggregate(total=Sum("balance_amount"))["total"]
        )
    except Exception as exc:  # noqa: BLE001 — gate never raises
        logger.info(
            "lifecycle.billing_gate.ledger_unreachable school_id=%s err=%s",
            school.id,
            type(exc).__name__,
        )
        return None
    return _as_decimal(total)


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

    # This used to ask ``apps.billing.entitlements.limits()`` for an
    # "outstanding_balance" key. That function only ever returns ENTITLEMENT /
    # QUOTA codes mapped to {"limit_value", "period_days"} — the key does not
    # exist anywhere in apps/billing — so the gate could only ever answer
    # "unknown" and no tenant was ever reported as owing anything. Read the
    # money records themselves instead.
    platform = _platform_debt(school)
    ledger = _tenant_ledger_outstanding(school)
    if platform is None and ledger is None:
        return BillingClearance(
            cleared=False,
            reason="billing state unavailable — operator dual-approve required",
            outstanding_balance=None,
            state="unknown",
        )

    amount = (platform or _zero()) + (ledger or _zero())
    if amount > _zero():
        parts = []
        if platform:
            parts.append(f"platform invoices {platform}")
        if ledger:
            parts.append(f"tenant ledger {ledger}")
        return BillingClearance(
            cleared=False,
            reason=f"outstanding balance {amount} ({', '.join(parts)})",
            outstanding_balance=amount,
            state="outstanding",
        )
    return BillingClearance(
        cleared=True,
        reason="zero balance",
        outstanding_balance=_zero(),
        state="cleared",
    )
