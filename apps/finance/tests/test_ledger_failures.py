"""Ledger integrity: non-posting guards and balanced journal lines."""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from django.test import TestCase
from django.utils import timezone

from apps.academics.models import AcademicYear, Classroom, Department, Specialty
from apps.finance.models import (
    ComplianceProfile,
    Invoice,
    InvoiceLine,
    JournalEntry,
    Payment,
    PaymentMethodCode,
)
from apps.finance.services import (
    post_invoice_to_ledger,
    post_payment_to_ledger,
    recalculate_invoice,
)
from apps.people.models import StudentProfile


class LedgerFailureGuardsTests(TestCase):
    def setUp(self):
        self.profile = ComplianceProfile.objects.create(
            name="Ledger Guard Profile",
            country_code="CM",
            currency_code="XAF",
            is_active=True,
        )
        self.year = AcademicYear.objects.create(
            name="2025/2026",
            start_date=date(2025, 9, 1),
            end_date=date(2026, 6, 30),
            is_active=True,
        )
        department = Department.objects.create(name="Science", code="SCI-LG")
        specialty = Specialty.objects.create(
            department=department, name="General", code="GEN-LG"
        )
        classroom = Classroom.objects.create(
            academic_year=self.year,
            department=department,
            name="Form 1",
            code="F1-LG",
        )
        self.student = StudentProfile.objects.create(
            first_name="Ledger",
            last_name="Guard",
            student_code="LG001",
            academic_year=self.year,
            classroom=classroom,
            specialty=specialty,
        )

    def test_post_payment_to_ledger_skips_non_positive_amount(self):
        invoice = Invoice.objects.create(
            profile=self.profile,
            academic_year=self.year,
            invoice_type=Invoice.InvoiceType.AR,
            status=Invoice.Status.ISSUED,
            student=self.student,
            total_amount=Decimal("50.00"),
            balance_amount=Decimal("50.00"),
            issued_date=timezone.now().date(),
        )
        payment = Payment(
            invoice=invoice,
            amount=Decimal("0.00"),
            method=PaymentMethodCode.CASH,
            paid_at=timezone.now(),
        )
        post_payment_to_ledger(payment)
        self.assertFalse(
            JournalEntry.objects.filter(
                source_type="payment", source_id=payment.id
            ).exists()
        )

    def test_post_invoice_to_ledger_skips_draft_and_zero_total(self):
        draft = Invoice.objects.create(
            profile=self.profile,
            academic_year=self.year,
            invoice_type=Invoice.InvoiceType.AR,
            status=Invoice.Status.DRAFT,
            student=self.student,
            total_amount=Decimal("100.00"),
            balance_amount=Decimal("100.00"),
            issued_date=timezone.now().date(),
        )
        post_invoice_to_ledger(draft)
        self.assertFalse(
            JournalEntry.objects.filter(source_type="invoice", source_id=draft.id).exists()
        )

        zero = Invoice(
            profile=self.profile,
            academic_year=self.year,
            invoice_type=Invoice.InvoiceType.AR,
            status=Invoice.Status.ISSUED,
            student=self.student,
            total_amount=Decimal("0.00"),
            balance_amount=Decimal("0.00"),
            issued_date=timezone.now().date(),
        )
        post_invoice_to_ledger(zero)
        self.assertFalse(JournalEntry.objects.filter(source_type="invoice").exists())

    def _invoice_with_line(self, amount: str) -> Invoice:
        invoice = Invoice.objects.create(
            profile=self.profile,
            academic_year=self.year,
            invoice_type=Invoice.InvoiceType.AR,
            status=Invoice.Status.ISSUED,
            student=self.student,
            total_amount=Decimal(amount),
            balance_amount=Decimal(amount),
            issued_date=timezone.now().date(),
        )
        InvoiceLine.objects.create(
            invoice=invoice,
            description="Tuition",
            quantity=Decimal("1.00"),
            unit_price=Decimal(amount),
            amount=Decimal(amount),
        )
        recalculate_invoice(invoice)
        invoice.refresh_from_db()
        return invoice

    def test_post_payment_to_ledger_posts_balanced_entry(self):
        invoice = self._invoice_with_line("75.00")
        payment = Payment.objects.create(
            invoice=invoice,
            student=self.student,
            amount=Decimal("75.00"),
            method=PaymentMethodCode.CASH,
            paid_at=timezone.now(),
            status="completed",
        )
        post_payment_to_ledger(payment)

        entry = JournalEntry.objects.get(source_type="payment", source_id=payment.id)
        debit_total = sum((line.debit for line in entry.lines.all()), Decimal("0.00"))
        credit_total = sum((line.credit for line in entry.lines.all()), Decimal("0.00"))
        self.assertEqual(debit_total, Decimal("75.00"))
        self.assertEqual(credit_total, Decimal("75.00"))

    def test_post_payment_to_ledger_is_idempotent_on_repeat(self):
        invoice = self._invoice_with_line("40.00")
        payment = Payment.objects.create(
            invoice=invoice,
            student=self.student,
            amount=Decimal("40.00"),
            method=PaymentMethodCode.BANK,
            paid_at=timezone.now(),
            status="completed",
        )
        post_payment_to_ledger(payment)
        post_payment_to_ledger(payment)
        self.assertEqual(
            JournalEntry.objects.filter(source_type="payment", source_id=payment.id).count(),
            1,
        )
