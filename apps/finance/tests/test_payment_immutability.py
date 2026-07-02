"""Payment final-state immutability (invoice/payment immutability audit).

Once a payment reaches a FINAL money state (completed / failed / cancelled /
refunded) its financial identity — amount, invoice, method — is read-only.
Corrections are SEPARATE entries (soft-delete reversal, RefundRequest), never
in-place rewrites. Status-only transitions (completed -> refunded, the
soft-delete's own cancelled flip) remain allowed, as do edits while the
payment is still pending/processing. System restore paths bypass the guard
via ``raw_save`` (DR) or the ``_allow_financial_edit`` escape hatch.

Sister invariant: Invoice already enforces Part F 25.1 (amounts immutable
once status is not DRAFT).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.academics.models import AcademicYear
from apps.finance.models import (
    ComplianceProfile,
    Invoice,
    InvoiceLine,
    Payment,
    PaymentMethodCode,
)


class PaymentImmutabilityTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.profile = ComplianceProfile.objects.create(
            name="Immutability Test", country_code="CM"
        )
        cls.year = AcademicYear.objects.create(
            name="2025/2026-imm",
            start_date=date(2025, 9, 1),
            end_date=date(2026, 6, 30),
        )
        cls.invoice = Invoice.objects.create(
            profile=cls.profile,
            academic_year=cls.year,
            reference="INV-IMMUTABLE-1",
            invoice_type=Invoice.InvoiceType.AR,
            status=Invoice.Status.ISSUED,
            total_amount=Decimal("500.00"),
            balance_amount=Decimal("500.00"),
        )
        InvoiceLine.objects.create(
            invoice=cls.invoice,
            description="Tuition",
            quantity=1,
            unit_price=Decimal("500.00"),
            amount=Decimal("500.00"),
        )

    def _payment(self, *, status="completed", amount="100.00"):
        return Payment.objects.create(
            invoice=self.invoice,
            amount=Decimal(amount),
            method=PaymentMethodCode.CASH,
            status=status,
        )

    def test_completed_payment_amount_is_immutable(self):
        p = self._payment(status="completed")
        p.amount = Decimal("150.00")
        with self.assertRaises(ValidationError):
            p.save()

    def test_completed_payment_method_is_immutable(self):
        p = self._payment(status="completed")
        p.method = PaymentMethodCode.BANK
        with self.assertRaises(ValidationError):
            p.save()

    def test_completed_payment_invoice_is_immutable(self):
        other = Invoice.objects.create(
            profile=self.profile,
            academic_year=self.year,
            reference="INV-IMMUTABLE-2",
            invoice_type=Invoice.InvoiceType.AR,
            status=Invoice.Status.ISSUED,
            total_amount=Decimal("300.00"),
            balance_amount=Decimal("300.00"),
        )
        p = self._payment(status="completed")
        p.invoice = other
        with self.assertRaises(ValidationError):
            p.save()

    def test_pending_payment_amount_still_editable(self):
        p = self._payment(status="pending", amount="100.00")
        p.amount = Decimal("120.00")
        p.save()
        p.refresh_from_db()
        self.assertEqual(p.amount, Decimal("120.00"))

    def test_status_only_transition_from_final_allowed(self):
        p = self._payment(status="completed")
        p.status = "refunded"
        p.save(update_fields=["status"])
        p.refresh_from_db()
        self.assertEqual(p.status, "refunded")

    def test_soft_delete_reversal_still_works_on_completed(self):
        p = self._payment(status="completed")
        deleted, _ = p.delete()
        self.assertEqual(deleted, 1)
        p.refresh_from_db()
        self.assertIsNotNone(p.deleted_at)
        self.assertEqual(p.status, "cancelled")

    def test_allow_financial_edit_escape_hatch(self):
        p = self._payment(status="completed")
        p._allow_financial_edit = True
        p.amount = Decimal("150.00")
        p.save()
        p.refresh_from_db()
        self.assertEqual(p.amount, Decimal("150.00"))
