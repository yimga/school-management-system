"""DB-level validation that not-received payments don't reduce invoice balance.

Wave 6a of the 2026-06-04 remediation: Invoice.computed_balance (and
recalculate_invoice) summed ALL payments, so a failed / cancelled / refunded
payment reduced the balance — flipping an invoice to PAID for money that never
arrived (or was returned). _NON_RECEIVED_PAYMENT_STATUSES are now excluded.
"""
from __future__ import annotations

from decimal import Decimal

from django.test import TestCase

from apps.finance.models import (
    ComplianceProfile,
    Invoice,
    InvoiceLine,
    Payment,
    PaymentMethodCode,
)
from apps.finance.services import recalculate_invoice
from apps.people.models import StudentProfile
from apps.schools.models import School


class InvoiceBalanceNotReceivedTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.school = School.objects.create(
            name="Balance School",
            slug="balance-school",
            subdomain="balance-school",
            is_active=True,
        )
        cls.profile = ComplianceProfile.objects.create(
            name="Balance Finance Profile",
            country_code="US",
            currency_code="USD",
            is_active=True,
        )
        cls.student = StudentProfile.objects.create(
            school=cls.school, first_name="Bal", last_name="Ance"
        )

    def _invoice(self, ref):
        invoice = Invoice.objects.create(
            school=self.school,
            profile=self.profile,
            student=self.student,
            invoice_type=Invoice.InvoiceType.AR,
            status=Invoice.Status.ISSUED,
            total_amount=Decimal("100.00"),
            balance_amount=Decimal("100.00"),
            reference=ref,
        )
        # A line so a payment-triggered recalc keeps total at 100.00 (recalc
        # derives total_amount from lines; zero lines would fail the >= 0.01 min).
        InvoiceLine.objects.create(
            invoice=invoice,
            description="Tuition",
            quantity=Decimal("1.00"),
            unit_price=Decimal("100.00"),
            amount=Decimal("100.00"),
        )
        return invoice

    def _pay(self, invoice, amount, status):
        return Payment.objects.create(
            school=self.school,
            invoice=invoice,
            student=self.student,
            amount=Decimal(amount),
            method=PaymentMethodCode.CASH,
            status=status,
        )

    def test_completed_payment_reduces_balance(self):
        inv = self._invoice("INV-COMPLETED")
        self._pay(inv, "40.00", "completed")
        self.assertEqual(inv.computed_balance, Decimal("60.00"))

    def test_failed_payment_does_not_reduce_balance(self):
        inv = self._invoice("INV-FAILED")
        self._pay(inv, "100.00", "failed")
        self.assertEqual(inv.computed_balance, Decimal("100.00"))

    def test_cancelled_payment_does_not_reduce_balance(self):
        inv = self._invoice("INV-CANCELLED")
        self._pay(inv, "100.00", "cancelled")
        self.assertEqual(inv.computed_balance, Decimal("100.00"))

    def test_refunded_payment_does_not_reduce_balance(self):
        inv = self._invoice("INV-REFUNDED")
        self._pay(inv, "100.00", "refunded")
        self.assertEqual(inv.computed_balance, Decimal("100.00"))

    def test_mixed_payments_only_count_received(self):
        inv = self._invoice("INV-MIXED")
        self._pay(inv, "30.00", "completed")
        self._pay(inv, "50.00", "failed")
        self._pay(inv, "20.00", "refunded")
        # Only the 30.00 completed counts → 70.00 outstanding.
        self.assertEqual(inv.computed_balance, Decimal("70.00"))

    def test_recalculate_invoice_excludes_not_received(self):
        inv = self._invoice("INV-RECALC")
        self._pay(inv, "100.00", "failed")
        recalculate_invoice(inv)
        inv.refresh_from_db()
        # balance_amount must NOT be driven to 0 by a failed payment.
        self.assertEqual(inv.balance_amount, Decimal("100.00"))
