"""Finance import → ledger closure for Migration Cloud.

Imported fee rows must become visible AR invoices (ISSUED/PAID), optional
historical Payment rows, and double-entry ledger posts — not silent DRAFT
shells with ``total_amount`` set but no ``InvoiceLine`` (``recalculate_invoice``
would zero them on the first payment sync).
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from datetime import datetime, time
from decimal import Decimal
from typing import Any

from django.core.exceptions import ValidationError
from django.db import DatabaseError, IntegrityError, transaction

from apps.migration_cloud.landers._helpers import coerce_date, coerce_decimal

logger = logging.getLogger(__name__)

_MIGRATION_PAYMENT_EXT_PREFIX = "mc-import:"


@contextmanager
def _suppress_import_finance_notifications():
    """Skip guardian invoice/payment pings for bulk historical import."""
    from apps.finance.notifications import _skip_new_invoice_notify

    token = _skip_new_invoice_notify.set(True)
    try:
        yield
    finally:
        _skip_new_invoice_notify.reset(token)


def resolve_import_paid_amount(row: dict[str, Any], total: Decimal) -> Decimal:
    """Derive collected amount from canonical finance row fields."""
    paid = coerce_decimal(row.get("paid_amount"))
    if paid is not None:
        return max(paid, Decimal("0.00"))
    balance = coerce_decimal(row.get("balance"))
    if balance is not None:
        return max(total - balance, Decimal("0.00"))
    return Decimal("0.00")


def _resolve_payment_method(row: dict[str, Any]) -> str:
    from apps.finance.models import PaymentMethodCode

    raw = (
        row.get("payment_method")
        or row.get("method")
        or row.get("payment_type")
        or ""
    )
    token = str(raw).strip().upper().replace(" ", "_").replace("-", "_")
    aliases = {
        "CASH": PaymentMethodCode.CASH,
        "BANK": PaymentMethodCode.BANK,
        "BANK_TRANSFER": PaymentMethodCode.BANK,
        "TRANSFER": PaymentMethodCode.BANK,
        "CARD": PaymentMethodCode.CARD,
        "MOMO": PaymentMethodCode.MTN_MOMO,
        "MTN": PaymentMethodCode.MTN_MOMO,
        "MTN_MOMO": PaymentMethodCode.MTN_MOMO,
        "ORANGE": PaymentMethodCode.ORANGE_MOMO,
        "ORANGE_MOMO": PaymentMethodCode.ORANGE_MOMO,
        "MPESA": PaymentMethodCode.MPESA,
        "CHECK": PaymentMethodCode.CHECK,
        "CHEQUE": PaymentMethodCode.CHECK,
        "WALLET": PaymentMethodCode.WALLET,
        "VOUCHER": PaymentMethodCode.VOUCHER,
    }
    if token in aliases:
        return aliases[token]
    for choice in PaymentMethodCode:
        if token == choice.value or token == choice.name:
            return choice.value
    return PaymentMethodCode.OTHER


def ensure_import_invoice_line(
    invoice,
    *,
    amount: Decimal,
    description: str,
) -> bool:
    """Ensure a single AR line backs ``recalculate_invoice`` totals."""
    from apps.finance.models import InvoiceLine

    existing = InvoiceLine.objects.filter(invoice_id=invoice.pk).first()
    if existing is not None:
        if existing.amount != amount or existing.description != (description or "Imported fee"):
            InvoiceLine.objects.filter(pk=existing.pk).update(
                description=(description or "Imported fee")[:200],
                quantity=Decimal("1.00"),
                unit_price=amount,
                amount=amount,
            )
            return True
        return False
    InvoiceLine.objects.create(
        invoice=invoice,
        description=(description or "Imported fee")[:200],
        quantity=Decimal("1.00"),
        unit_price=amount,
        amount=amount,
    )
    return True


def _apply_import_payment_ledger(payment) -> None:
    """Ledger + balance sync without guardian notification fan-out."""
    from apps.finance.services import (
        allocate_payment_to_payer_shares,
        post_payment_to_ledger,
        recalculate_invoice,
    )

    if not payment or not payment.invoice_id:
        return
    recalculate_invoice(payment.invoice)
    try:
        allocate_payment_to_payer_shares(payment)
    except (ImportError, AttributeError, TypeError, ValueError) as exc:
        logger.debug(
            "finance_ledger: payer-share allocation skipped payment=%s: %s",
            getattr(payment, "pk", "?"),
            exc,
        )
    post_payment_to_ledger(payment)


@transaction.atomic
def sync_imported_finance_row(
    invoice,
    row: dict[str, Any],
    *,
    reference: str,
    school,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Post-import closure: line, ISSUED status, optional payment, ledger."""
    from apps.finance.models import Invoice, Payment
    from apps.finance.services import post_invoice_to_ledger, recalculate_invoice

    amount = coerce_decimal(row.get("amount")) or invoice.total_amount or Decimal("0.00")
    if amount < Decimal("0.01"):
        return {"skipped": True, "reason": "zero_amount"}

    description = (row.get("description") or invoice.notes or "Imported fee").strip()
    paid_amount = resolve_import_paid_amount(row, amount)
    if paid_amount > amount:
        paid_amount = amount

    if dry_run:
        return {
            "dry_run": True,
            "paid_amount": str(paid_amount),
            "would_issue": True,
        }

    outcome: dict[str, Any] = {
        "invoice_id": invoice.pk,
        "reference": reference,
        "paid_amount": str(paid_amount),
    }

    with _suppress_import_finance_notifications():
        line_created = ensure_import_invoice_line(
            invoice, amount=amount, description=description
        )
        outcome["line_created"] = line_created

        if invoice.invoice_type != Invoice.InvoiceType.AR:
            Invoice.objects.filter(pk=invoice.pk).update(
                invoice_type=Invoice.InvoiceType.AR
            )
            invoice.invoice_type = Invoice.InvoiceType.AR

        recalculate_invoice(invoice)
        invoice.refresh_from_db()

        if paid_amount >= Decimal("0.01"):
            ext_ref = f"{_MIGRATION_PAYMENT_EXT_PREFIX}{reference}"
            school_id = getattr(school, "pk", None) or getattr(invoice, "school_id", None)
            payment_qs = Payment.objects.filter(
                invoice_id=invoice.pk,
                external_reference=ext_ref,
            )
            if school_id is not None:
                payment_qs = payment_qs.filter(school_id=school_id)
            payment = payment_qs.first()
            method = _resolve_payment_method(row)
            paid_at = coerce_date(row.get("payment_date") or row.get("paid_date"))
            defaults = {
                "amount": paid_amount,
                "method": method,
                "status": "completed",
                "student_id": invoice.student_id,
                "school_id": getattr(school, "pk", None) or getattr(invoice, "school_id", None),
                "purpose": "tuition",
                "description": f"Migration import for {reference}",
                "reference": f"MC {reference}",
            }
            if payment is None:
                payment = Payment(
                    invoice=invoice,
                    external_reference=ext_ref,
                    **defaults,
                )
                if paid_at is not None:
                    from django.utils import timezone as dj_tz

                    combined = datetime.combine(paid_at, time.min)
                    payment.paid_at = (
                        dj_tz.make_aware(combined)
                        if dj_tz.is_naive(combined)
                        else combined
                    )
                payment.save()
                outcome["payment_created"] = True
            else:
                changed = False
                for field, value in defaults.items():
                    if getattr(payment, field) != value:
                        setattr(payment, field, value)
                        changed = True
                if changed:
                    payment.save(update_fields=list(defaults.keys()))
                outcome["payment_created"] = False
            _apply_import_payment_ledger(payment)
            outcome["payment_id"] = payment.pk
        else:
            post_invoice_to_ledger(invoice)
            outcome["payment_created"] = False

        invoice.refresh_from_db()
        outcome["status"] = invoice.status
        outcome["balance_amount"] = str(invoice.balance_amount)
    return outcome


def assess_finance_ledger_readiness(school) -> dict[str, Any]:
    """Counts draft/import invoices that still need ledger closure."""
    from apps.finance.models import Invoice, JournalEntry

    if school is None:
        return {"ready": False, "reason": "no_school"}

    qs = Invoice.objects.filter(school=school).exclude(
        status__in=[Invoice.Status.VOID, Invoice.Status.DRAFT]
    )
    issued_without_ledger = 0
    for inv in qs.only("pk", "status", "total_amount")[:500]:
        if inv.total_amount <= 0:
            continue
        if not JournalEntry.objects.filter(
            source_type="invoice", source_id=inv.pk
        ).exists():
            issued_without_ledger += 1

    draft_with_total = Invoice.objects.filter(
        school=school,
        status=Invoice.Status.DRAFT,
        total_amount__gte=Decimal("0.01"),
    ).count()

    return {
        "ready": draft_with_total == 0 and issued_without_ledger == 0,
        "draft_invoices_with_total": draft_with_total,
        "issued_without_ledger": issued_without_ledger,
    }


def ensure_finance_ledger_closure(
    school,
    *,
    invoice_ids: list[int] | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Backfill lines + ISSUED + ledger for invoices landed without closure."""
    from apps.finance.models import Invoice, InvoiceLine, Payment
    from apps.finance.services import post_invoice_to_ledger, recalculate_invoice

    if school is None:
        return {"skipped": True, "reason": "no_school"}

    qs = Invoice.objects.filter(school=school)
    if invoice_ids:
        qs = qs.filter(pk__in=invoice_ids)
    else:
        qs = qs.filter(
            status=Invoice.Status.DRAFT,
            total_amount__gte=Decimal("0.01"),
        )

    closed = 0
    payments_linked = 0
    errors: list[str] = []

    for invoice in qs.iterator():
        try:
            amount = invoice.total_amount
            if dry_run:
                closed += 1
                continue
            with _suppress_import_finance_notifications():
                if not InvoiceLine.objects.filter(invoice_id=invoice.pk).exists():
                    ensure_import_invoice_line(
                        invoice,
                        amount=amount,
                        description=(invoice.notes or "Imported fee"),
                    )
                recalculate_invoice(invoice)
                invoice.refresh_from_db()
                ext_prefix = f"{_MIGRATION_PAYMENT_EXT_PREFIX}"
                payment_qs = Payment.objects.filter(
                    invoice_id=invoice.pk,
                    school_id=school.pk,
                    external_reference__startswith=ext_prefix,
                )
                if not payment_qs.exists():
                    post_invoice_to_ledger(invoice)
                else:
                    payment = payment_qs.first()
                    if payment is not None:
                        _apply_import_payment_ledger(payment)
                        payments_linked += 1
                closed += 1
        except (DatabaseError, IntegrityError, ValidationError, TypeError, ValueError) as exc:
            msg = f"invoice {invoice.pk}: {type(exc).__name__}: {exc}"
            errors.append(msg)
            logger.warning("finance_ledger closure failed: %s", msg, exc_info=True)

    return {
        "invoices_closed": closed,
        "payments_linked": payments_linked,
        "errors": errors[:10],
        "readiness_after": assess_finance_ledger_readiness(school),
    }


def ensure_finance_ledger_closure_for_bundle(bundle, *, dry_run: bool = False) -> dict[str, Any]:
    """Bundle-scoped wrapper — closes finance rows from this apply's created ids."""
    from apps.automation.models import MigrationRun

    school = getattr(bundle, "school", None)
    if school is None:
        return {"skipped": True, "reason": "no_school"}

    invoice_ids: list[int] = []
    for run in MigrationRun.objects.filter(
        school=school,
        execution_summary__bundle_id=bundle.pk,
        migration_type__startswith="finance:",
    ):
        for source in (
            run.execution_summary if isinstance(run.execution_summary, dict) else {},
            run.rollback_snapshot if isinstance(run.rollback_snapshot, dict) else {},
        ):
            for raw_id in source.get("created_ids") or []:
                try:
                    invoice_ids.append(int(raw_id))
                except (TypeError, ValueError):
                    continue

    invoice_ids = list(dict.fromkeys(invoice_ids))

    if not invoice_ids:
        return ensure_finance_ledger_closure(school, dry_run=dry_run)

    return ensure_finance_ledger_closure(
        school, invoice_ids=invoice_ids, dry_run=dry_run
    )
