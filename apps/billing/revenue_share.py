"""Processor referral revenue-share attribution (Phase 1 of the platform revenue build).

Business model (BYO gateway, local-first): parent fees settle to the SCHOOL's own
merchant account — the platform never holds the money. Under a referral /
record-and-invoice arrangement, the PROCESSOR pays the platform a rebate on the volume
the platform routes to it. This module records that attribution per settled payment so
the platform can invoice / reconcile the rebate. No funds move through the platform here.

Producer: wired from ``apps/finance/signals.py`` on ``Payment`` post_save (best-effort,
never breaks a payment save). Idempotent on (school, source_payment_id) — ``Payment.pk``
is a per-tenant AutoField and collides across tenant schemas, so school disambiguates.

Honesty: the referral rate defaults to 0, so ``rebate_amount`` is 0 until a real
per-processor rate is configured. The ledger records routed GMV truthfully and never
invents revenue before a partner deal exists.
"""

from __future__ import annotations

import logging
from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)

_CENTS = Decimal("0.01")
_HUNDRED = Decimal("100")
_SETTLED_STATUS = "completed"
# Statuses on which an existing accrual must be voided (money not, or no longer, received).
_UNSETTLED_STATUSES = frozenset({"refunded", "failed", "cancelled"})


def _platform_default_currency() -> str:
    return str(getattr(settings, "PLATFORM_DEFAULT_CURRENCY", "USD") or "USD")


def resolve_processor_revshare_percent(processor_code: str, school=None) -> Decimal:
    """The referral rate (percent) applied to a processor's routed volume.

    Resolution: a per-processor override
    (``PLATFORM_PROCESSOR_REVSHARE_PERCENT_BY_CODE`` dict, keyed by lowercased processor
    code) wins; otherwise the platform default ``PLATFORM_PROCESSOR_REVSHARE_PERCENT``.
    Both default to 0 — a partner rate must be set deliberately, so this never fabricates
    a rebate. ``school`` is accepted for a future per-tenant override and is unused today.
    """
    code = (processor_code or "").strip().lower()
    by_code = getattr(settings, "PLATFORM_PROCESSOR_REVSHARE_PERCENT_BY_CODE", None) or {}
    raw = None
    if code and isinstance(by_code, dict) and code in by_code:
        raw = by_code[code]
    if raw in (None, ""):
        raw = getattr(settings, "PLATFORM_PROCESSOR_REVSHARE_PERCENT", None)
    if raw in (None, ""):
        return Decimal("0")
    try:
        pct = Decimal(str(raw))
    except (InvalidOperation, TypeError, ValueError):
        logger.warning("invalid PLATFORM_PROCESSOR_REVSHARE_PERCENT %r; treating as 0", raw)
        return Decimal("0")
    return pct if pct > 0 else Decimal("0")


def _resolve_processor_and_method(payment) -> tuple[str, str]:
    """(processor_code, method_code) for a payment.

    processor_code is the PSP that owes the rebate — the configured gateway on the
    payment's PaymentMethod (stripe/flutterwave/paystack/...), falling back to the rail
    ``method`` code (momo/bank/cash/...) when no gateway is set (e.g. offline/cash).
    """
    method_code = (getattr(payment, "method", "") or "").strip()
    processor = ""
    pm = getattr(payment, "payment_method", None)
    if pm is not None:
        processor = (getattr(pm, "gateway", "") or "").strip()
    if not processor:
        processor = method_code
    return processor.lower(), method_code


def _resolve_school(payment):
    school = getattr(payment, "school", None)
    if school is None and getattr(payment, "invoice_id", None):
        school = getattr(getattr(payment, "invoice", None), "school", None)
    return school


def _school_ref(school) -> str:
    return (str(getattr(school, "slug", "") or getattr(school, "pk", "") or ""))[:64]


def record_processor_revenue_share_attribution(payment):
    """Upsert the rev-share accrual for one settled payment. Idempotent.

    Returns the accrual row, or None when there is nothing to attribute (payment not
    settled, no school, or net GMV <= 0). On a payment that has since been refunded /
    failed / cancelled, voids any prior accrual instead of creating one.
    """
    from .models import ProcessorRevenueShareAccrual

    status = getattr(payment, "status", None)
    school = _resolve_school(payment)
    if school is None:
        return None

    if status in _UNSETTLED_STATUSES:
        return _void_accrual(school, payment)
    if status != _SETTLED_STATUS:
        return None

    amount = Decimal(str(getattr(payment, "amount", None) or "0"))
    refunded = Decimal(str(getattr(payment, "refunded_amount", None) or "0"))
    gross = (amount - refunded).quantize(_CENTS)
    if gross <= 0:
        return _void_accrual(school, payment)

    processor_code, method_code = _resolve_processor_and_method(payment)
    pct = resolve_processor_revshare_percent(processor_code, school)
    rebate = (gross * pct / _HUNDRED).quantize(_CENTS)
    currency = ((getattr(payment, "currency_code", "") or "").strip().upper()
                or _platform_default_currency())[:3]
    occurred = getattr(payment, "paid_at", None) or timezone.now()

    # tenant-isolation-allow: idempotency-lookup-scoped-by-school-fk-and-payment-pk
    existing = ProcessorRevenueShareAccrual.objects.filter(
        school=school, source_payment_id=payment.pk
    ).first()
    if existing is None:
        return ProcessorRevenueShareAccrual.objects.create(
            school=school,
            school_ref=_school_ref(school),
            source_payment_id=payment.pk,
            processor_code=processor_code[:40],
            method_code=method_code[:32],
            gross_amount=gross,
            currency_code=currency,
            rev_share_percent=pct,
            rebate_amount=rebate,
            status=ProcessorRevenueShareAccrual.Status.ACCRUED,
            occurred_at=occurred,
        )

    # Refresh amounts. Preserve a downstream status (INVOICED/RECONCILED): re-opening it
    # to ACCRUED would silently un-invoice a reconciled rebate. If the amount changed
    # after invoicing, flag it for a clawback review rather than mutating status here.
    Status = ProcessorRevenueShareAccrual.Status
    fields = ["processor_code", "method_code", "gross_amount", "currency_code",
              "rev_share_percent", "rebate_amount", "occurred_at", "updated_at"]
    if existing.status in (Status.INVOICED, Status.RECONCILED) and (
        existing.gross_amount != gross or existing.rebate_amount != rebate
    ):
        meta = dict(existing.metadata or {})
        meta["amount_changed_after_invoice"] = {
            "prev_gross": str(existing.gross_amount),
            "new_gross": str(gross),
        }
        existing.metadata = meta
        fields.append("metadata")
    elif existing.status != Status.RECONCILED:
        existing.status = Status.ACCRUED
        fields.append("status")

    existing.processor_code = processor_code[:40]
    existing.method_code = method_code[:32]
    existing.gross_amount = gross
    existing.currency_code = currency
    existing.rev_share_percent = pct
    existing.rebate_amount = rebate
    existing.occurred_at = occurred
    existing.save(update_fields=fields)
    return existing


def _void_accrual(school, payment):
    from .models import ProcessorRevenueShareAccrual

    # tenant-isolation-allow: void-scoped-by-school-fk-and-payment-pk
    existing = ProcessorRevenueShareAccrual.objects.filter(
        school=school, source_payment_id=payment.pk
    ).first()
    if existing is None or existing.status == ProcessorRevenueShareAccrual.Status.VOIDED:
        return existing
    existing.status = ProcessorRevenueShareAccrual.Status.VOIDED
    existing.rebate_amount = Decimal("0.00")
    existing.save(update_fields=["status", "rebate_amount", "updated_at"])
    return existing


def summarize_processor_revenue_share(
    *, period_start=None, period_end=None, processor_code=None, statuses=None
):
    """Reconciliation reader: routed GMV + owed rebate grouped by processor + currency.

    This is the invoice/reconciliation basis — 'you routed X volume to processor P in
    currency C; the agreed rate makes the rebate Y'. Defaults to ACCRUED + INVOICED rows
    (excludes VOIDED). Platform-wide by design (a processor rebate spans all schools).
    """
    from django.db.models import Count, Sum

    from .models import ProcessorRevenueShareAccrual

    Status = ProcessorRevenueShareAccrual.Status
    if statuses is None:
        statuses = [Status.ACCRUED, Status.INVOICED]
    # tenant-isolation-allow: platform-wide-processor-reconciliation-reader-not-tenant-scoped
    qs = ProcessorRevenueShareAccrual.objects.filter(status__in=statuses)
    if period_start is not None:
        qs = qs.filter(occurred_at__gte=period_start)
    if period_end is not None:
        qs = qs.filter(occurred_at__lt=period_end)
    if processor_code:
        qs = qs.filter(processor_code=processor_code.strip().lower())

    by_processor = list(
        qs.values("processor_code", "currency_code")
        .annotate(
            gross=Sum("gross_amount"),
            rebate=Sum("rebate_amount"),
            payments=Count("id"),
        )
        .order_by("processor_code", "currency_code")
    )
    totals_by_currency: dict[str, dict[str, Decimal]] = {}
    for row in by_processor:
        cur = row["currency_code"]
        bucket = totals_by_currency.setdefault(
            cur, {"gross": Decimal("0.00"), "rebate": Decimal("0.00")}
        )
        bucket["gross"] += row["gross"] or Decimal("0.00")
        bucket["rebate"] += row["rebate"] or Decimal("0.00")
    return {"by_processor_currency": by_processor, "totals_by_currency": totals_by_currency}
