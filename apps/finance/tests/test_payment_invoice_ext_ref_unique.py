"""DB-enforced payment idempotency (Shopify pillar)."""

from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.test.utils import override_settings

from apps.academics.models import AcademicYear
from apps.finance.models import ComplianceProfile, Invoice, Payment, PaymentMethodCode
from apps.schools.models import School


@override_settings(SEND_FINANCE_SIGNALS=False)
class PaymentInvoiceExtRefUniqueTests(TestCase):
    def test_duplicate_external_reference_on_same_invoice_rejected(self):
        school = School.objects.create(
            name="Pay Unique School",
            slug="pay-unique",
            subdomain="pay-unique",
            is_active=True,
        )
        profile = ComplianceProfile.objects.create(name="Test", country_code="CM")
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
        Payment.objects.create(
            invoice=invoice,
            school=school,
            amount=Decimal("10.00"),
            method=PaymentMethodCode.CASH,
            external_reference="psp_evt_dup_1",
        )
        with self.assertRaises((IntegrityError, ValidationError)):
            with transaction.atomic():
                Payment.objects.create(
                    invoice=invoice,
                    school=school,
                    amount=Decimal("10.00"),
                    method=PaymentMethodCode.CASH,
                    external_reference="psp_evt_dup_1",
                )
