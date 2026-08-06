"""Settlement reconciliation.

Rolls up each tenant's *recorded* payments per (region, payment_method,
period) into ``finance.PaymentReconciliation`` and surfaces the classic
reconciliation signal: a gateway payment booked as ``completed`` in our ledger
that carries **no settlement transaction id** — money the ledger claims was
collected online but for which no PSP confirmation was ever recorded.

RECORDING ONLY. This job never moves money, never calls a payment gateway and
never mutates a ``Payment``. It only computes rollups and writes
``PaymentReconciliation`` rows, so it is safe to run unattended on a beat.

Before this module ``PaymentReconciliation`` had a model + admin but **zero
creators** — the reconciliation surface was inert. This is its producer.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Optional

from django.utils import timezone

# Payment statuses that represent money actually taken into the ledger for a
# period. "refunded" is included because the original collection still landed —
# the returned portion is captured separately via refunded_amount.
RECONCILABLE_STATUSES = ("completed", "refunded")

# PaymentMethod.gateway values that are NOT an external PSP, so no settlement
# transaction id is expected (cash desk, bank slip, manual reconciliation).
NON_PSP_GATEWAYS = {"", "manual"}

ZERO = Decimal("0.00")


def previous_calendar_month(today: Optional[date] = None) -> tuple[date, date]:
    """Return (first_day, last_day) of the calendar month before ``today``."""
    today = today or timezone.now().date()
    first_of_this_month = today.replace(day=1)
    last_of_prev = first_of_this_month - timedelta(days=1)
    first_of_prev = last_of_prev.replace(day=1)
    return first_of_prev, last_of_prev


def _as_date(value) -> Optional[date]:
    if value is None or isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def run_settlement_reconciliation(
    period_start: Optional[date] = None,
    period_end: Optional[date] = None,
    dry_run: bool = False,
    actor=None,
) -> dict:
    """Reconcile one tenant schema for ``[period_start, period_end]`` inclusive.

    Must be called inside the tenant's DB context (the beat wrapper handles
    that). Groups recorded payments by their payment method (which carries the
    authoritative region for the PSP account), computes payment / refund / fee
    totals and the net, and flags gateway collections lacking a settlement id.

    Returns a summary dict; when ``dry_run`` is True nothing is written.
    """
    # Local import so importing this module never drags the ORM at settings load.
    from apps.finance.models import Payment, PaymentReconciliation

    period_start = _as_date(period_start)
    period_end = _as_date(period_end)
    if period_start is None or period_end is None:
        period_start, period_end = previous_calendar_month()

    payments = (
        Payment.objects.filter(  # tenant-isolation-allow: celery-finance-beat-caller-or-region-scoped-reviewed
            status__in=RECONCILABLE_STATUSES,
            paid_at__date__gte=period_start,
            paid_at__date__lte=period_end,
            payment_method__isnull=False,
            deleted_at__isnull=True,
        )
        .select_related("payment_method", "payment_method__region")
    )

    groups: dict = {}
    skipped_no_region = 0
    for p in payments.iterator():
        method = p.payment_method
        region = getattr(method, "region", None)
        if region is None:
            # Cannot key a PaymentReconciliation row (region is required).
            skipped_no_region += 1
            continue
        g = groups.setdefault(
            method.pk,
            {
                "method": method,
                "region": region,
                "total_payments": ZERO,
                "total_refunds": ZERO,
                "total_fees": ZERO,
                "unsettled_amount": ZERO,
                "unsettled_count": 0,
                "count": 0,
            },
        )
        amount = p.amount or ZERO
        g["total_payments"] += amount
        g["total_refunds"] += p.refunded_amount or ZERO
        g["total_fees"] += p.platform_fee or ZERO
        g["count"] += 1

        gateway = (method.gateway or "").strip().lower()
        is_psp = gateway not in NON_PSP_GATEWAYS
        has_settlement_id = bool((p.gateway_transaction_id or "").strip())
        if is_psp and p.status == "completed" and not has_settlement_id:
            # Booked as collected online, but no PSP settlement token was ever
            # recorded — the exact mismatch reconciliation exists to catch.
            g["unsettled_amount"] += amount
            g["unsettled_count"] += 1

    rows = []
    written = 0
    discrepancies = 0
    now = timezone.now()
    for g in groups.values():
        net = g["total_payments"] - g["total_refunds"] - g["total_fees"]
        disc = g["unsettled_amount"]
        has_discrepancy = disc > ZERO
        status = "discrepancy" if has_discrepancy else "reconciled"
        if has_discrepancy:
            discrepancies += 1
            notes = (
                f"{g['unsettled_count']} gateway payment(s) totalling {disc} "
                f"booked as completed without a settlement transaction id."
            )
        else:
            notes = ""

        rows.append(
            {
                "region": str(g["region"]),
                "payment_method": g["method"].name,
                "count": g["count"],
                "total_payments": str(g["total_payments"]),
                "total_refunds": str(g["total_refunds"]),
                "total_fees": str(g["total_fees"]),
                "net_amount": str(net),
                "discrepancy_amount": str(disc),
                "status": status,
            }
        )

        if dry_run:
            continue

        defaults = {
            "total_payments": g["total_payments"],
            "total_refunds": g["total_refunds"],
            "total_fees": g["total_fees"],
            "net_amount": net,
            "status": status,
            "discrepancy_amount": disc,
            "discrepancy_notes": notes,
            # Only a clean rollup counts as reconciled; a discrepancy row is left
            # un-timestamped so it reads as "needs a human", not "closed".
            "reconciled_at": None if has_discrepancy else now,
            "reconciled_by": None if has_discrepancy else actor,
        }
        PaymentReconciliation.objects.update_or_create(  # tenant-isolation-allow: celery-finance-beat-caller-or-region-scoped-reviewed
            region=g["region"],
            payment_method=g["method"],
            period_start=period_start,
            period_end=period_end,
            defaults=defaults,
        )
        written += 1

    return {
        "period_start": period_start.isoformat(),
        "period_end": period_end.isoformat(),
        "groups": len(groups),
        "written": written,
        "discrepancies": discrepancies,
        "skipped_no_region": skipped_no_region,
        "dry_run": dry_run,
        "rows": rows,
    }
