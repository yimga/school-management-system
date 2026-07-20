"""A payment must be stamped with the school's real currency, never a blind USD.

``Payment.currency_code`` defaulted to the literal ``"USD"``, so every payment
recorded without an explicit currency was booked in dollars regardless of the
school. A Buea bursar taking 100,000 XAF over the counter created a USD row, and
any figure summed across payments was meaningless. The identical blind-USD bug
was already fixed once on the fractional ledger; this closes it on the Payment
row itself.

Must-FIRE: the no-currency-passed case is the one that regressed.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from django.test import TestCase, override_settings

from apps.academics.models import AcademicYear
from apps.finance.models import ComplianceProfile, Invoice, Payment, PaymentMethodCode
from apps.schools.models import School


class PaymentCurrencyResolutionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.school = School.objects.create(
            name="Buea Currency School",
            slug="buea-currency-school",
            subdomain="buea-currency-school",
            country_code="CM",
            currency="XAF",
            is_active=True,
        )
        cls.year = AcademicYear.objects.create(
            school=cls.school,
            name="2025/2026",
            start_date=date(2025, 9, 1),
            end_date=date(2026, 7, 31),
            is_active=True,
        )
        cls.profile = ComplianceProfile.objects.create(
            name="Buea Currency", country_code="CM", currency_code="XAF"
        )

    def _invoice(self, ref="INV-CUR-1"):
        return Invoice.objects.create(
            profile=self.profile,
            school=self.school,
            academic_year=self.year,
            reference=ref,
            invoice_type=Invoice.InvoiceType.AR,
            status=Invoice.Status.ISSUED,
            issued_date=date(2025, 9, 5),
            due_date=date(2025, 10, 5),
            total_amount=Decimal("165000.00"),
            balance_amount=Decimal("165000.00"),
        )

    def test_invoice_payment_without_currency_is_not_stamped_usd(self):
        """The regressed case: a Cameroon payment booked in dollars."""
        invoice = self._invoice()
        payment = Payment.objects.create(
            invoice=invoice,
            amount=Decimal("100000.00"),
            method=PaymentMethodCode.CASH,
            status="completed",
        )
        payment.refresh_from_db()
        self.assertEqual(payment.currency_code, "XAF")

    def test_explicit_currency_is_respected(self):
        invoice = self._invoice("INV-CUR-2")
        payment = Payment.objects.create(
            invoice=invoice,
            amount=Decimal("10.00"),
            method=PaymentMethodCode.CASH,
            status="completed",
            currency_code="USD",
        )
        payment.refresh_from_db()
        self.assertEqual(payment.currency_code, "USD")

    def test_standalone_payment_resolves_from_school(self):
        payment = Payment.objects.create(
            school=self.school, amount=Decimal("5000.00"), purpose="tuition"
        )
        payment.refresh_from_db()
        self.assertEqual(payment.currency_code, "XAF")

    @override_settings(PLATFORM_DEFAULT_CURRENCY="GBP")
    def test_falls_back_to_platform_default_when_nothing_resolves(self):
        payment = Payment.objects.create(amount=Decimal("1.00"), purpose="other")
        payment.refresh_from_db()
        self.assertEqual(payment.currency_code, "GBP")

    def test_currency_code_is_never_left_blank(self):
        payment = Payment.objects.create(amount=Decimal("1.00"), purpose="other")
        payment.refresh_from_db()
        self.assertTrue(payment.currency_code)
        self.assertEqual(len(payment.currency_code), 3)
