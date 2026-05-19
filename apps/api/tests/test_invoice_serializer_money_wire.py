"""Invoice/payment API serializers emit amount_str money wire format."""

from datetime import date
from decimal import Decimal

from django.test import TestCase
from django.test.utils import override_settings

from apps.academics.models import AcademicYear
from apps.api.serializers import InvoiceSerializer, PaymentSerializer
from apps.finance.models import ComplianceProfile, Invoice, Payment, PaymentMethodCode
from apps.schools.models import School


@override_settings(SEND_FINANCE_SIGNALS=False)
class InvoiceSerializerMoneyWireTests(TestCase):
    def test_invoice_money_fields_are_strings(self):
        school = School.objects.create(
            name="Wire School",
            slug="wire-school",
            subdomain="wire-school",
            is_active=True,
        )
        profile = ComplianceProfile.objects.create(name="CM", country_code="CM")
        year = AcademicYear.objects.create(
            name="2025/2026",
            start_date=date(2025, 9, 1),
            end_date=date(2026, 6, 30),
        )
        invoice = Invoice.objects.create(
            school=school,
            profile=profile,
            academic_year=year,
            total_amount=Decimal("100.00"),
            balance_amount=Decimal("100.00"),
            status=Invoice.Status.ISSUED,
        )
        data = InvoiceSerializer(invoice).data
        self.assertEqual(data["total_amount"], "100.00")
        self.assertEqual(data["balance_amount"], "100.00")
        self.assertIsInstance(data["paid_amount"], str)
        self.assertIsInstance(data["balance"], str)

    def test_payment_amount_is_string(self):
        school = School.objects.create(
            name="Pay Wire",
            slug="pay-wire",
            subdomain="pay-wire",
            is_active=True,
        )
        profile = ComplianceProfile.objects.create(name="CM2", country_code="CM")
        year = AcademicYear.objects.create(
            name="2026/2027",
            start_date=date(2026, 9, 1),
            end_date=date(2027, 6, 30),
        )
        invoice = Invoice.objects.create(
            school=school,
            profile=profile,
            academic_year=year,
            total_amount=Decimal("50.00"),
            balance_amount=Decimal("50.00"),
            status=Invoice.Status.ISSUED,
        )
        payment = Payment.objects.create(
            invoice=invoice,
            school=school,
            amount=Decimal("0.10") + Decimal("0.20"),
            method=PaymentMethodCode.CASH,
        )
        data = PaymentSerializer(payment).data
        self.assertEqual(data["amount"], "0.30")
