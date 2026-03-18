from __future__ import annotations

from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from apps.academics.models import AcademicYear, Classroom, Department, Specialty
from apps.finance.models import ComplianceProfile, Invoice, PaymentMethodCode
from apps.finance.services import generate_payment_link
from apps.people.models import StudentProfile
from apps.siteconfig.models import Integration


class GeneratePaymentLinkTests(TestCase):
    def setUp(self):
        self.profile = ComplianceProfile.objects.create(
            name="Test Profile",
            country_code="CM",
            currency_code="XAF",
            currency_symbol="XAF",
            timezone="Africa/Douala",
            chart_template=ComplianceProfile.ChartTemplate.OHADA,
            min_wage=Decimal("60000"),
            default_hours_per_week=Decimal("40"),
            overtime_multiplier=Decimal("1.5"),
            annual_leave_days=21,
            maternity_leave_days=84,
            is_active=True,
        )
        self.year = AcademicYear.objects.create(
            name="2025/2026",
            start_date="2025-09-01",
            end_date="2026-06-30",
            is_active=True,
        )
        self.department = Department.objects.create(name="Science", code="SCI")
        self.specialty = Specialty.objects.create(
            department=self.department, name="General", code="GEN"
        )
        self.classroom = Classroom.objects.create(
            academic_year=self.year,
            department=self.department,
            name="Form 1",
            code="F1",
        )
        self.student = StudentProfile.objects.create(
            first_name="Jane",
            last_name="Doe",
            student_code="STU001",
            academic_year=self.year,
            classroom=self.classroom,
            specialty=self.specialty,
        )
        Integration.objects.create(
            name="MTN MoMo",
            provider="payments",
            enabled=True,
            config={
                "provider_slug": "mtn_momo",
                "base_url": "https://pay.example/checkout",
                "secret": "secret-key",
                "callback_path": "/finance/payments/webhook/mtn_momo/",
            },
        )

    def _create_invoice(self, total: Decimal, balance: Decimal) -> Invoice:
        return Invoice.objects.create(
            profile=self.profile,
            academic_year=self.year,
            invoice_type=Invoice.InvoiceType.AR,
            status=Invoice.Status.ISSUED,
            student=self.student,
            total_amount=total,
            balance_amount=balance,
            issued_date=timezone.now().date(),
        )

    def test_generate_payment_link_uses_balance_amount(self):
        invoice = self._create_invoice(Decimal("100.00"), Decimal("45.50"))
        link = generate_payment_link(invoice, method=PaymentMethodCode.MTN_MOMO)
        self.assertIn("amount=45.50", link["url"])

    def test_generate_payment_link_never_uses_negative_balance(self):
        invoice = self._create_invoice(Decimal("100.00"), Decimal("-5.00"))
        link = generate_payment_link(invoice, method=PaymentMethodCode.MTN_MOMO)
        self.assertIn("amount=0.00", link["url"])
