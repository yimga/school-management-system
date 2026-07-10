"""Kit-fee invoicing — Decimal-exact amount + idempotent get_or_create.

``raise_kit_fee_invoice`` raises a finance AR ``Invoice`` (+ single line) for a
membership team's mandatory ``TeamKitFee``. All money is ``Decimal`` (never
float), and a second call is idempotent (keyed on profile/school/student/AR/ref).
"""

from __future__ import annotations

from decimal import Decimal

from apps.athletics.models import TeamKitFee
from apps.athletics.services.fees import raise_kit_fee_invoice
from apps.athletics.tests.base import BaseAthleticsTestCase
from apps.finance.models import ComplianceProfile, Invoice


class KitFeeInvoiceTests(BaseAthleticsTestCase):
    def setUp(self):
        super().setUp()
        self.profile = ComplianceProfile.objects.create(
            name="Athletics Fees", country_code="CM", is_active=True
        )
        self.membership = self.add_member(self.fx)
        self.fee = TeamKitFee.objects.create(
            school=self.fx.school,
            team=self.fx.team,
            label="Home + away kit",
            amount=Decimal("120.00"),
            is_mandatory=True,
            is_active=True,
        )

    def test_invoice_amount_is_decimal_equal_to_fee(self):
        invoice = raise_kit_fee_invoice(membership=self.membership)
        self.assertIsInstance(invoice.total_amount, Decimal)
        self.assertEqual(invoice.total_amount, self.fee.amount)
        self.assertEqual(invoice.invoice_type, Invoice.InvoiceType.AR)
        self.assertEqual(invoice.student_id, self.membership.student_id)
        # The single line carries the same Decimal amount.
        line = invoice.lines.get()
        self.assertIsInstance(line.amount, Decimal)
        self.assertEqual(line.amount, self.fee.amount)

    def test_second_call_is_idempotent(self):
        first = raise_kit_fee_invoice(membership=self.membership)
        second = raise_kit_fee_invoice(membership=self.membership)
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(
            Invoice.objects.filter(
                school=self.fx.school, student_id=self.membership.student_id,
                invoice_type=Invoice.InvoiceType.AR,
            ).count(),
            1,
        )

    def test_no_kit_fee_raises_value_error(self):
        self.fee.delete()
        with self.assertRaises(ValueError):
            raise_kit_fee_invoice(membership=self.membership)

    def test_inactive_fee_is_not_invoiced(self):
        self.fee.is_active = False
        self.fee.save(update_fields=["is_active"])
        with self.assertRaises(ValueError):
            raise_kit_fee_invoice(membership=self.membership)
