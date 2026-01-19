from __future__ import annotations

from decimal import Decimal
from typing import Iterable

from django.db import transaction
from django.utils import timezone

from apps.people.models import StudentProfile

from .models import (
    ComplianceProfile,
    FeePlan,
    Invoice,
    InvoiceLine,
    JournalEntry,
    JournalLine,
    LedgerAccount,
    Payment,
)


def _account(profile: ComplianceProfile, code: str, name: str, account_type: str) -> LedgerAccount:
    account, _ = LedgerAccount.objects.get_or_create(
        profile=profile,
        code=code,
        defaults={
            "name": name,
            "account_type": account_type,
            "is_active": True,
        },
    )
    return account


def post_invoice_to_ledger(invoice: Invoice) -> None:
    if invoice.status in {Invoice.Status.DRAFT, Invoice.Status.VOID}:
        return
    if invoice.total_amount <= 0:
        return
    entry = JournalEntry.objects.filter(source_type="invoice", source_id=invoice.id).first()

    profile = invoice.profile
    if invoice.invoice_type == Invoice.InvoiceType.AP:
        debit_account = _account(profile, "611", "Purchases and Services", LedgerAccount.AccountType.EXPENSE)
        credit_account = _account(profile, "401", "Trade Payables", LedgerAccount.AccountType.LIABILITY)
    else:
        debit_account = _account(profile, "411", "Student Receivables", LedgerAccount.AccountType.ASSET)
        credit_account = _account(profile, "706", "Tuition Revenue", LedgerAccount.AccountType.INCOME)

    if entry:
        entry.entry_date = invoice.issued_date
        entry.reference = invoice.reference or f"INV-{invoice.id}"
        entry.memo = invoice.notes or ""
        entry.posted_at = entry.posted_at or timezone.now()
        entry.save(update_fields=["entry_date", "reference", "memo", "posted_at"])
        entry.lines.all().delete()
    else:
        entry = JournalEntry.objects.create(
            profile=profile,
            entry_date=invoice.issued_date,
            reference=invoice.reference or f"INV-{invoice.id}",
            memo=invoice.notes or "",
            source_type="invoice",
            source_id=invoice.id,
            posted_at=timezone.now(),
        )
    JournalLine.objects.create(
        entry=entry,
        account=debit_account,
        description=invoice.reference or "Invoice",
        debit=invoice.total_amount,
        credit=Decimal("0.00"),
    )
    JournalLine.objects.create(
        entry=entry,
        account=credit_account,
        description=invoice.reference or "Invoice",
        debit=Decimal("0.00"),
        credit=invoice.total_amount,
    )


def post_payment_to_ledger(payment: Payment) -> None:
    if payment.amount <= 0:
        return
    entry = JournalEntry.objects.filter(source_type="payment", source_id=payment.id).first()

    invoice = payment.invoice
    profile = invoice.profile

    cash_account = _account(profile, "531", "Cash", LedgerAccount.AccountType.ASSET)
    bank_account = _account(profile, "512", "Bank", LedgerAccount.AccountType.ASSET)
    mobile_account = _account(profile, "514", "Mobile Money", LedgerAccount.AccountType.ASSET)

    if payment.method in {Payment.Method.CASH}:
        debit_account = cash_account
    elif payment.method in {Payment.Method.MTN_MOMO, Payment.Method.ORANGE_MOMO}:
        debit_account = mobile_account
    else:
        debit_account = bank_account

    if invoice.invoice_type == Invoice.InvoiceType.AP:
        credit_account = debit_account
        debit_account = _account(profile, "401", "Trade Payables", LedgerAccount.AccountType.LIABILITY)
    else:
        credit_account = _account(profile, "411", "Student Receivables", LedgerAccount.AccountType.ASSET)

    if entry:
        entry.entry_date = payment.paid_at.date()
        entry.reference = payment.receipt_number or f"PAY-{payment.id}"
        entry.memo = payment.reference or ""
        entry.posted_at = entry.posted_at or timezone.now()
        entry.save(update_fields=["entry_date", "reference", "memo", "posted_at"])
        entry.lines.all().delete()
    else:
        entry = JournalEntry.objects.create(
            profile=profile,
            entry_date=payment.paid_at.date(),
            reference=payment.receipt_number or f"PAY-{payment.id}",
            memo=payment.reference or "",
            source_type="payment",
            source_id=payment.id,
            posted_at=timezone.now(),
        )
    JournalLine.objects.create(
        entry=entry,
        account=debit_account,
        description=invoice.reference or "Payment",
        debit=payment.amount,
        credit=Decimal("0.00"),
    )
    JournalLine.objects.create(
        entry=entry,
        account=credit_account,
        description=invoice.reference or "Payment",
        debit=Decimal("0.00"),
        credit=payment.amount,
    )


def _invoice_status(total: Decimal, balance: Decimal) -> str:
    if total <= 0:
        return Invoice.Status.DRAFT
    if balance <= 0:
        return Invoice.Status.PAID
    if balance < total:
        return Invoice.Status.PARTIAL
    return Invoice.Status.ISSUED


def recalculate_invoice(invoice: Invoice) -> None:
    total = Decimal("0.00")
    for line in invoice.lines.all():
        total += line.amount

    paid = Decimal("0.00")
    for payment in invoice.payments.all():
        paid += payment.amount

    balance = max(total - paid, Decimal("0.00"))
    invoice.total_amount = total
    invoice.balance_amount = balance
    invoice.status = _invoice_status(total, balance)
    invoice.save(update_fields=["total_amount", "balance_amount", "status", "updated_at"])
    post_invoice_to_ledger(invoice)


def apply_payment(payment: Payment) -> None:
    recalculate_invoice(payment.invoice)
    post_payment_to_ledger(payment)


def _student_for_plan(plan: FeePlan) -> Iterable[StudentProfile]:
    return StudentProfile.objects.filter(
        academic_year=plan.academic_year,
        classroom=plan.classroom,
        specialty=plan.specialty,
        is_active=True,
    ).order_by("last_name", "first_name")


@transaction.atomic
def create_fee_invoices(
    *,
    plan: FeePlan,
    profile: ComplianceProfile,
    issued_date=None,
    due_date=None,
) -> list[Invoice]:
    issued_date = issued_date or timezone.now().date()
    fee_items = list(plan.items.all())
    invoices: list[Invoice] = []

    for student in _student_for_plan(plan):
        invoice, created = Invoice.objects.get_or_create(
            profile=profile,
            academic_year=plan.academic_year,
            student=student,
            invoice_type=Invoice.InvoiceType.AR,
            reference=f"FEE-{plan.academic_year.name}-{student.student_code}",
            defaults={
                "issued_date": issued_date,
                "due_date": due_date,
                "status": Invoice.Status.ISSUED,
            },
        )
        if not created:
            invoice.issued_date = issued_date
            invoice.due_date = due_date
            invoice.save(update_fields=["issued_date", "due_date", "updated_at"])

        if created or not invoice.lines.exists():
            InvoiceLine.objects.filter(invoice=invoice).delete()
            for item in fee_items:
                InvoiceLine.objects.create(
                    invoice=invoice,
                    description=item.name,
                    quantity=Decimal("1.00"),
                    unit_price=item.amount,
                    amount=item.amount,
                    fee_item=item,
                )

        recalculate_invoice(invoice)
        invoices.append(invoice)

    return invoices
