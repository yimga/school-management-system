"""Fractional payment ledger — partial posts and enrollment clearance."""

from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from apps.academics.models import AcademicYear
from apps.finance.fractional_ledger_services import (
    enrollment_clearance_for_invoice,
    post_partial_payment,
)
from apps.finance.models import ComplianceProfile, Invoice, InvoiceLine
from apps.finance.models_fractional_ledger import FractionalPaymentLedger
from apps.schools.models import School


class FractionalLedgerTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(name="Ledger School", is_active=True)
        self.profile = ComplianceProfile.objects.create(name="Ledger", country_code="CM")
        self.year = AcademicYear.objects.create(
            name="2025/2026",
            start_date="2025-09-01",
            end_date="2026-06-30",
            is_active=True,
        )
        self.invoice = Invoice.objects.create(
            profile=self.profile,
            school=self.school,
            academic_year=self.year,
            reference="INV-FRAC-001",
            invoice_type=Invoice.InvoiceType.AR,
            status=Invoice.Status.ISSUED,
            issued_date=timezone.localdate(),
            due_date=timezone.localdate(),
            total_amount=Decimal("1000.00"),
            balance_amount=Decimal("1000.00"),
        )
        InvoiceLine.objects.create(
            invoice=self.invoice,
            description="Tuition",
            quantity=Decimal("1"),
            unit_price=Decimal("1000.00"),
            amount=Decimal("1000.00"),
        )

    def test_three_partial_posts_converge_and_idempotent(self):
        post_partial_payment(
            school=self.school,
            invoice=self.invoice,
            amount=Decimal("200.00"),
            idempotency_key="cash-1",
        )
        r2 = post_partial_payment(
            school=self.school,
            invoice=self.invoice,
            amount=Decimal("300.00"),
            idempotency_key="cash-2",
        )
        r3 = post_partial_payment(
            school=self.school,
            invoice=self.invoice,
            amount=Decimal("500.00"),
            idempotency_key="cash-3",
        )
        dup = post_partial_payment(
            school=self.school,
            invoice=self.invoice,
            amount=Decimal("999.00"),
            idempotency_key="cash-2",
        )
        self.assertEqual(r2.pk, dup.pk)
        self.assertEqual(r3.running_paid_total, Decimal("1000.00"))
        self.assertEqual(r3.invoice_balance_after, Decimal("0.00"))
        self.assertTrue(r3.enrollment_clearance_met)
        self.assertEqual(
            FractionalPaymentLedger.objects.filter(invoice=self.invoice).count(), 3
        )

    def test_clearance_helper_matches_ledger(self):
        post_partial_payment(
            school=self.school,
            invoice=self.invoice,
            amount=Decimal("600.00"),
            idempotency_key="half-plus",
        )
        self.assertTrue(enrollment_clearance_for_invoice(self.invoice, school=self.school))
