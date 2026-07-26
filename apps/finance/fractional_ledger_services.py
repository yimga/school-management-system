"""Post irregular partial payments and compute enrollment clearance."""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

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


def _resolve_currency_code(invoice: Invoice) -> str:
    """Resolve the invoice's real currency — never blind-default to USD.

    ``Invoice`` has NO ``currency_code`` field (only the optional canonical
    ``currency`` FK to registries.CurrencyRegistry), so a
    ``getattr(invoice, "currency_code", None)`` read always fell through and
    stamped every fractional row "USD" — wrong for every non-USD tenant
    (XAF/NGN/GBP...). Mirrors the fallback order already used by
    ``Invoice.save()`` and ``reconcile_offline_payment_intent``: canonical
    currency FK -> ComplianceProfile.currency_code -> USD.
    """
    code = (getattr(getattr(invoice, "currency", None), "code", "") or "").strip()
    if code:
        return code[:3].upper()
    code = (getattr(getattr(invoice, "profile", None), "currency_code", "") or "").strip()
    if code:
        return code[:3].upper()
    return "USD"


def _ledger_paid_total(invoice: Invoice) -> Decimal:
    agg = FractionalPaymentLedger.objects.filter(
        school=invoice.school, invoice=invoice
    ).aggregate(s=Sum("amount"))
    return Decimal(agg["s"] or "0")


def _invoice_subtotal(invoice: Invoice) -> Decimal | None:
    """Pre-tax subtotal = sum of invoice line amounts (mirrors recalculate_invoice).

    Returns ``None`` when the invoice has no lines to sum, so the caller can tell
    "no derivable tax" apart from a genuine zero subtotal.
    """
    from apps.finance.models import InvoiceLine

    agg = InvoiceLine.objects.filter(invoice_id=invoice.pk).aggregate(s=Sum("amount"))
    return None if agg["s"] is None else Decimal(agg["s"])


def _tax_component_for(
    amount: Decimal, invoice_total: Decimal, subtotal: Decimal | None
) -> Decimal:
    """Portion of ``amount`` attributable to tax, by proportional allocation.

    ``recalculate_invoice`` builds ``total_amount = subtotal + VAT``, so the tax
    fraction of the tax-inclusive total is ``(total - subtotal) / total`` and each
    partial collection carries that same fraction (the standard cash-basis method).

    Pure and DB-free (all inputs passed in) so the allocation math is unit-tested
    without a database. Returns ``0`` — never negative, never > ``amount`` — when
    the total is non-positive or the subtotal is unknown / not below the total (no
    derivable tax → attribute nothing).
    """
    if invoice_total <= Decimal("0") or subtotal is None:
        return Decimal("0")
    if subtotal < Decimal("0") or subtotal >= invoice_total:
        return Decimal("0")
    tax_fraction = (invoice_total - subtotal) / invoice_total
    return (amount * tax_fraction).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


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
    quantized_amount = amount.quantize(Decimal("0.01"))
    running = (prior + amount).quantize(Decimal("0.01"))
    balance_after = max(Decimal("0"), (invoice_total - running).quantize(Decimal("0.01")))
    clearance = running >= _clearance_threshold(school, invoice_total)
    # Snapshot the tax portion of THIS collection at post time (cash-basis VAT).
    # Additive/informational only — does not touch amount / running / balance.
    tax_component = _tax_component_for(
        quantized_amount, invoice_total, _invoice_subtotal(invoice)
    )

    row = FractionalPaymentLedger.objects.create(
        school=school,
        invoice=invoice,
        student=student,
        amount=quantized_amount,
        tax_component=tax_component,
        currency_code=_resolve_currency_code(invoice),
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


def vat_collected_for_invoice(invoice: Invoice, *, school=None) -> Decimal:
    """VAT actually collected on this invoice via fractional (cash/MoMo) partials.

    Sum of the per-row ``tax_component`` snapshots — the amount of tax a cash-basis
    tenant has genuinely received (as opposed to invoiced), which is what it must
    remit. Tenant-scoped: constrained to ``school`` (resolved from the invoice when
    not passed) so one tenant's collections never leak into another's return.
    """
    resolved_school = school if school is not None else getattr(invoice, "school", None)
    agg = FractionalPaymentLedger.objects.filter(
        school=resolved_school, invoice=invoice
    ).aggregate(s=Sum("tax_component"))
    return Decimal(agg["s"] or "0")


def vat_collected_for_school(school, *, since=None, until=None) -> Decimal:
    """Total fractional-collected VAT for a school over an optional post-date window.

    Feeds a cash-basis VAT remittance report: ``sum(tax_component)`` across every
    partial post the school received, optionally bounded by ``posted_at`` in
    ``[since, until]``. Tenant-scoped by ``school``.
    """
    qs = FractionalPaymentLedger.objects.filter(school=school)
    if since is not None:
        qs = qs.filter(posted_at__gte=since)
    if until is not None:
        qs = qs.filter(posted_at__lte=until)
    agg = qs.aggregate(s=Sum("tax_component"))
    return Decimal(agg["s"] or "0")
