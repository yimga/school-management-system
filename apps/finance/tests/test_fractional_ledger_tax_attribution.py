"""M26: cash-basis VAT attribution on fractional (partial) payments.

A tenant on cash-basis VAT must remit tax proportional to cash actually
collected. The fractional sub-ledger now snapshots the tax portion of each
partial post (``tax_component``) so "VAT collected" is derivable from irregular
cash/MoMo instalments — without changing what the payer is charged (amount /
running / balance are byte-identical to before).
"""

from decimal import Decimal

from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from apps.academics.models import AcademicYear
from apps.finance.fractional_ledger_services import (
    _tax_component_for,
    post_partial_payment,
    vat_collected_for_invoice,
    vat_collected_for_school,
)
from apps.finance.models import ComplianceProfile, Invoice, InvoiceLine
from apps.finance.models_fractional_ledger import FractionalPaymentLedger
from apps.schools.models import School


class TaxComponentPureTests(SimpleTestCase):
    """Pure proportional-allocation math (no DB)."""

    def test_half_payment_carries_half_the_tax(self):
        # subtotal 1000 + 19.25% VAT -> total 1192.50, tax 192.50.
        # A half payment (596.25) carries exactly half the tax.
        self.assertEqual(
            _tax_component_for(Decimal("596.25"), Decimal("1192.50"), Decimal("1000")),
            Decimal("96.25"),
        )

    def test_full_payment_carries_all_the_tax(self):
        self.assertEqual(
            _tax_component_for(Decimal("1192.50"), Decimal("1192.50"), Decimal("1000")),
            Decimal("192.50"),
        )

    def test_zero_vat_invoice_attributes_nothing(self):
        # subtotal == total -> no derivable tax.
        self.assertEqual(
            _tax_component_for(Decimal("500"), Decimal("1000"), Decimal("1000")),
            Decimal("0"),
        )

    def test_unknown_subtotal_attributes_nothing(self):
        self.assertEqual(
            _tax_component_for(Decimal("500"), Decimal("1000"), None), Decimal("0")
        )

    def test_non_positive_total_attributes_nothing(self):
        self.assertEqual(
            _tax_component_for(Decimal("500"), Decimal("0"), Decimal("0")), Decimal("0")
        )

    def test_subtotal_above_total_is_guarded(self):
        # Defensive: a malformed invoice (subtotal > total) never yields negative tax.
        self.assertEqual(
            _tax_component_for(Decimal("500"), Decimal("1000"), Decimal("1200")),
            Decimal("0"),
        )

    def test_small_partial_rounds_half_up(self):
        self.assertEqual(
            _tax_component_for(Decimal("100.00"), Decimal("1192.50"), Decimal("1000")),
            Decimal("16.14"),
        )


class FractionalTaxAttributionDBTests(TestCase):
    """End-to-end: producer snapshots tax; report helpers sum it; tenant-scoped."""

    def setUp(self):
        self.school = School.objects.create(
            name="VAT School", slug="vat-school", subdomain="vat-school", is_active=True
        )
        self.other_school = School.objects.create(
            name="VAT Other", slug="vat-other", subdomain="vat-other", is_active=True
        )
        self.profile = ComplianceProfile.objects.create(name="VAT", country_code="CM")
        self.year = AcademicYear.objects.create(
            name="2025/2026",
            start_date="2025-09-01",
            end_date="2026-06-30",
            is_active=True,
        )
        # Tax-inclusive total (subtotal 1000 + 19.25% VAT), exactly as
        # recalculate_invoice would leave it.
        self.invoice = self._make_invoice("INV-VAT-1", Decimal("1192.50"), Decimal("1000.00"))

    def _make_invoice(self, ref, total, line_amount):
        inv = Invoice.objects.create(
            profile=self.profile,
            school=self.school,
            academic_year=self.year,
            reference=ref,
            invoice_type=Invoice.InvoiceType.AR,
            status=Invoice.Status.ISSUED,
            issued_date=timezone.localdate(),
            due_date=timezone.localdate(),
            total_amount=line_amount,
            balance_amount=line_amount,
        )
        InvoiceLine.objects.create(
            invoice=inv,
            description="Tuition",
            quantity=Decimal("1"),
            unit_price=line_amount,
            amount=line_amount,
        )
        # Creating the line recomputes total_amount from lines (this test profile
        # carries no vat_rate). Stamp the tax-inclusive total directly — exactly
        # the state recalculate_invoice leaves when the ComplianceProfile HAS a
        # vat_rate (total = subtotal + VAT). .update() bypasses the save hook so
        # it is not clobbered; refresh so the in-memory instance matches the DB.
        Invoice.objects.filter(pk=inv.pk).update(
            total_amount=total, balance_amount=total
        )
        inv.refresh_from_db()
        # Fixture guard: a tax-inclusive fixture MUST have total > line subtotal,
        # else a silent 0-tax fixture would false-green the whole suite.
        assert inv.total_amount == total, (inv.total_amount, total)
        return inv

    def test_partial_snapshots_proportional_tax(self):
        row = post_partial_payment(
            school=self.school,
            invoice=self.invoice,
            amount=Decimal("596.25"),
            idempotency_key="vat-half",
        )
        self.assertEqual(row.tax_component, Decimal("96.25"))
        # Charging fields untouched by the attribution.
        self.assertEqual(row.amount, Decimal("596.25"))
        self.assertEqual(row.invoice_balance_after, Decimal("596.25"))

    def test_vat_collected_helpers_sum_snapshots(self):
        post_partial_payment(
            school=self.school, invoice=self.invoice,
            amount=Decimal("596.25"), idempotency_key="vat-a",
        )
        post_partial_payment(
            school=self.school, invoice=self.invoice,
            amount=Decimal("300.00"), idempotency_key="vat-b",
        )
        # 96.25 + (300 * 192.50/1192.50 = 48.43) = 144.68
        expected = Decimal("96.25") + Decimal("48.43")
        self.assertEqual(vat_collected_for_invoice(self.invoice, school=self.school), expected)
        self.assertEqual(vat_collected_for_school(self.school), expected)

    def test_zero_vat_invoice_attributes_no_tax(self):
        inv = self._make_invoice("INV-VAT-0", Decimal("1000.00"), Decimal("1000.00"))
        row = post_partial_payment(
            school=self.school, invoice=inv,
            amount=Decimal("500.00"), idempotency_key="novat",
        )
        self.assertEqual(row.tax_component, Decimal("0.00"))
        self.assertEqual(vat_collected_for_invoice(inv, school=self.school), Decimal("0"))

    def test_idempotent_repost_does_not_double_count_tax(self):
        post_partial_payment(
            school=self.school, invoice=self.invoice,
            amount=Decimal("596.25"), idempotency_key="vat-dup",
        )
        post_partial_payment(
            school=self.school, invoice=self.invoice,
            amount=Decimal("596.25"), idempotency_key="vat-dup",
        )
        self.assertEqual(
            FractionalPaymentLedger.objects.filter(invoice=self.invoice).count(), 1
        )
        self.assertEqual(vat_collected_for_invoice(self.invoice, school=self.school), Decimal("96.25"))

    def test_vat_collected_is_tenant_scoped(self):
        # A post booked under another tenant never enters this school's VAT return.
        post_partial_payment(
            school=self.other_school, invoice=self.invoice,
            amount=Decimal("596.25"), idempotency_key="vat-cross",
        )
        self.assertEqual(vat_collected_for_school(self.school), Decimal("0"))
        self.assertEqual(
            vat_collected_for_invoice(self.invoice, school=self.school), Decimal("0")
        )
        self.assertEqual(
            vat_collected_for_school(self.other_school), Decimal("96.25")
        )
