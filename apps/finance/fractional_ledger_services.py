"""Post irregular partial payments and compute enrollment clearance."""

from __future__ import annotations

from decimal import Decimal

from django.db import transaction
from django.db.models import Sum

from apps.finance.models import Invoice
from apps.finance.models_fractional_ledger import FractionalPaymentLedger


def _invoice_total(invoice: Invoice) -> Decimal:
    total = getattr(invoice, "total_amount", None)
    if total is not None:
        return Decimal(total)
    lines = getattr(invoice, "lines", None)
    if lines is not None:
        agg = lines.aggregate(s=Sum("amount"))["s"]
        if agg is not None:
            return Decimal(agg)
    return Decimal(getattr(invoice, "amount", "0") or "0")


def _clearance_threshold(school, invoice_total: Decimal) -> Decimal:
    settings_raw = getattr(school, "settings", None) or {}
    finance_cfg = settings_raw.get("finance") if isinstance(settings_raw, dict) else {}
    if not isinstance(finance_cfg, dict):
        finance_cfg = {}
    pct = finance_cfg.get("enrollment_clearance_percent")
    if pct is not None:
        try:
            return (invoice_total * Decimal(str(pct)) / Decimal("100")).quantize(Decimal("0.01"))
        except (ArithmeticError, ValueError, TypeError):
            pass
    return (invoice_total * Decimal("0.50")).quantize(Decimal("0.01"))


def _ledger_paid_total(invoice: Invoice) -> Decimal:
    agg = FractionalPaymentLedger.objects.filter(
        school=invoice.school, invoice=invoice
    ).aggregate(s=Sum("amount"))
    return Decimal(agg["s"] or "0")


@transaction.atomic
def post_partial_payment(
    *,
    school,
    invoice: Invoice,
    amount: Decimal,
    source: str = FractionalPaymentLedger.Source.CASH_COUNTER,
    idempotency_key: str = "",
    student=None,
    note: str = "",
) -> FractionalPaymentLedger:
    """Record a partial payment; idempotent on (school, idempotency_key) when key set."""
    if amount <= Decimal("0"):
        raise ValueError("amount must be positive")
    if idempotency_key:
        existing = FractionalPaymentLedger.objects.filter(
            school=school, idempotency_key=idempotency_key
        ).first()
        if existing:
            return existing

    invoice_total = _invoice_total(invoice)
    prior = _ledger_paid_total(invoice)
    running = (prior + amount).quantize(Decimal("0.01"))
    balance_after = max(Decimal("0"), (invoice_total - running).quantize(Decimal("0.01")))
    clearance = running >= _clearance_threshold(school, invoice_total)

    row = FractionalPaymentLedger.objects.create(
        school=school,
        invoice=invoice,
        student=student,
        amount=amount.quantize(Decimal("0.01")),
        currency_code=str(getattr(invoice, "currency_code", None) or "USD")[:3],
        running_paid_total=running,
        invoice_balance_after=balance_after,
        source=source,
        idempotency_key=idempotency_key or "",
        enrollment_clearance_met=clearance,
        note=note[:255],
    )
    return row


def enrollment_clearance_for_invoice(invoice: Invoice, *, school) -> bool:
    """Whether cumulative fractional posts meet enrollment clearance threshold."""
    invoice_total = _invoice_total(invoice)
    paid = _ledger_paid_total(invoice)
    return paid >= _clearance_threshold(school, invoice_total)


def student_enrollment_blocked_for_unpaid(student, academic_year, *, school=None) -> bool:
    """Whether a student should be blocked/flagged for unpaid fees this year.

    Enrollment / result-visibility gating consults BOTH ledgers:
      * the regular ``Invoice.computed_balance`` (Payment-model receipts), and
      * the fractional sub-ledger (irregular cash / mobile-money partial posts).

    A student is blocked when at least one non-void invoice still carries a
    positive regular balance AND that same invoice has NOT met the tenant's
    fractional enrollment-clearance threshold. An invoice whose partial posts
    have reached the threshold no longer blocks, even if the regular Payment
    ledger has not been reconciled — this is the headline micro-finance loop
    (pay enough irregular instalments → clear to enroll / see results).

    Tenant-scoped: every invoice query is constrained to ``school`` (resolved
    from the student when not passed explicitly) so a clearance computed for one
    tenant can never leak across schools.
    """
    resolved_school = school if school is not None else getattr(student, "school", None)
    if resolved_school is None:
        return False

    invoices = Invoice.objects.filter(
        school=resolved_school,
        student=student,
        academic_year=academic_year,
    ).exclude(status=Invoice.Status.VOID)

    for inv in invoices:
        if inv.computed_balance <= Decimal("0.00"):
            continue
        if enrollment_clearance_for_invoice(inv, school=resolved_school):
            continue
        return True
    return False
