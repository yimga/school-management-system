"""process_refund_request: the producer that makes a RefundRequest actually
reduce collected revenue.

Before this producer existed, a RefundRequest (created e.g. for an overpayment)
sat 'pending' forever, Payment.status="refunded" had no writer, and marking a
request 'processed' in admin did nothing to the ledger — so refunded money kept
counting as received on every paid/outstanding tally. These tests pin the
producer: partial refunds net down the payment, full refunds flip it to
'refunded', the invoice balance recomputes, and the operation is idempotent and
bounded (no over-refund, no double-apply).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.academics.models import AcademicYear
from apps.finance.models import (
    ComplianceProfile,
    Invoice,
    InvoiceLine,
    Payment,
    PaymentMethodCode,
    RefundRequest,
)
from apps.finance.services import RefundProcessingError, process_refund_request
from apps.siteconfig.models import RegionConfig

User = get_user_model()


class RefundRequestProcessingTests(TestCase):
    def setUp(self):
        self.profile = ComplianceProfile.objects.create(
            name="Refund Test", country_code="CM"
        )
        self.year = AcademicYear.objects.create(
            name="2025/2026-refund",
            start_date=date(2025, 9, 1),
            end_date=date(2026, 6, 30),
        )
        self.region, _ = RegionConfig.objects.get_or_create(
            code="TST",
            defaults={
                "name": "Test",
                "default_language": "en",
                "timezone": "UTC",
                "date_format": "DD/MM/YYYY",
            },
        )
        self.user = User.objects.create_user("refund-admin", "ra@test.com", "pass")

    def _invoice_with_payment(self, total="500.00", paid="500.00"):
        invoice = Invoice.objects.create(
            profile=self.profile,
            academic_year=self.year,
            reference=f"INV-REFUND-{id(object()):x}",
            invoice_type=Invoice.InvoiceType.AR,
            status=Invoice.Status.ISSUED,
            total_amount=Decimal(total),
            balance_amount=Decimal(total),
        )
        InvoiceLine.objects.create(
            invoice=invoice,
            description="Tuition",
            quantity=1,
            unit_price=Decimal(total),
            amount=Decimal(total),
        )
        payment = Payment.objects.create(
            invoice=invoice,
            amount=Decimal(paid),
            method=PaymentMethodCode.CASH,
            status="completed",
        )
        return invoice, payment

    def _refund(self, payment, amount, status="pending"):
        return RefundRequest.objects.create(
            payment=payment,
            region=self.region,
            amount=Decimal(amount),
            reason="overpayment",
            description="test refund",
            status=status,
            requested_by=self.user,
        )

    def test_partial_refund_nets_payment_and_raises_balance(self):
        invoice, payment = self._invoice_with_payment(total="500.00", paid="500.00")
        self.assertEqual(invoice.computed_balance, Decimal("0.00"))

        refund = self._refund(payment, "200.00")
        process_refund_request(refund, processed_by=self.user)

        payment.refresh_from_db()
        self.assertEqual(payment.refunded_amount, Decimal("200.00"))
        # Partial refund → payment stays 'completed', only the net counts.
        self.assertEqual(payment.status, "completed")

        invoice.refresh_from_db()
        self.assertEqual(invoice.computed_balance, Decimal("200.00"))
        self.assertEqual(invoice.balance_amount, Decimal("200.00"))

        refund.refresh_from_db()
        self.assertEqual(refund.status, "processed")
        self.assertIsNotNone(refund.processed_at)

    def test_full_refund_flips_status_to_refunded(self):
        invoice, payment = self._invoice_with_payment(total="500.00", paid="500.00")
        refund = self._refund(payment, "500.00")
        process_refund_request(refund, processed_by=self.user)

        payment.refresh_from_db()
        self.assertEqual(payment.refunded_amount, Decimal("500.00"))
        self.assertEqual(payment.status, "refunded")

        invoice.refresh_from_db()
        # Fully refunded payment is excluded entirely → whole invoice outstanding.
        self.assertEqual(invoice.computed_balance, Decimal("500.00"))
        self.assertEqual(invoice.balance_amount, Decimal("500.00"))

    def test_processing_is_idempotent(self):
        _invoice, payment = self._invoice_with_payment()
        refund = self._refund(payment, "200.00")
        process_refund_request(refund)
        # Re-processing the same (now 'processed') request must not double-refund.
        process_refund_request(refund)
        process_refund_request(refund)

        payment.refresh_from_db()
        self.assertEqual(payment.refunded_amount, Decimal("200.00"))

    def test_over_refund_is_rejected(self):
        _invoice, payment = self._invoice_with_payment(total="500.00", paid="500.00")
        # A first refund of 300 leaves 200 refundable.
        process_refund_request(self._refund(payment, "300.00"))
        # A second refund of 300 would total 600 > 500 → rejected, ledger untouched.
        with self.assertRaises(RefundProcessingError):
            process_refund_request(self._refund(payment, "300.00"))

        payment.refresh_from_db()
        self.assertEqual(payment.refunded_amount, Decimal("300.00"))

    def test_rejected_request_cannot_be_processed(self):
        _invoice, payment = self._invoice_with_payment()
        refund = self._refund(payment, "100.00", status="rejected")
        with self.assertRaises(RefundProcessingError):
            process_refund_request(refund)

        payment.refresh_from_db()
        self.assertEqual(payment.refunded_amount, Decimal("0.00"))
