"""Invoice PDF receipt: WeasyPrint path + request context for receipt template."""

from __future__ import annotations

import sys
from decimal import Decimal
from unittest.mock import MagicMock, patch

from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import User
from apps.academics.models import AcademicYear, Classroom, Department, Specialty
from apps.finance.models import (
    ComplianceProfile,
    Invoice,
    Payment,
    PaymentMethodCode,
)
from apps.people.models import StudentProfile


class InvoiceReceiptPdfTests(TestCase):
    """Mock weasyprint so CI without native deps can still exercise the view."""

    def setUp(self):
        self.profile = ComplianceProfile.objects.create(
            name="Cameroon",
            country_code="CM",
            currency_code="XAF",
            currency_symbol="FCFA",
            timezone="Africa/Douala",
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
            department=self.department,
            name="General",
            code="GEN",
        )
        self.classroom = Classroom.objects.create(
            academic_year=self.year,
            department=self.department,
            name="Form 3",
            code="F3",
        )
        self.student = StudentProfile.objects.create(
            first_name="Test",
            last_name="Student",
            student_code="STU-RCP",
            academic_year=self.year,
            classroom=self.classroom,
            specialty=self.specialty,
        )
        User.objects.create_superuser(
            username="receipt_admin",
            password="Pass_1234",
            email="receipt_admin@example.com",
        )
        self.invoice = Invoice.objects.create(
            profile=self.profile,
            academic_year=self.year,
            invoice_type=Invoice.InvoiceType.AR,
            status=Invoice.Status.ISSUED,
            student=self.student,
            total_amount=Decimal("25000.00"),
            balance_amount=Decimal("24000.00"),
            issued_date="2026-02-01",
        )
        # Avoid full apply_payment / recalculate_invoice in this isolated PDF wiring test.
        with patch("apps.finance.signals.apply_payment"):
            self.payment = Payment.objects.create(
                invoice=self.invoice,
                amount=Decimal("1000.00"),
                method=PaymentMethodCode.CASH,
            )
        self.client.login(username="receipt_admin", password="Pass_1234")

    def test_invoice_receipt_returns_pdf_with_mocked_weasyprint(self):
        fake_weasy = MagicMock()
        fake_html_instance = MagicMock()
        fake_html_instance.write_pdf.return_value = b"%PDF-1.4 test"
        fake_weasy.HTML = MagicMock(return_value=fake_html_instance)

        url = reverse("finance:invoice_receipt", args=[self.invoice.id])
        with patch.dict(sys.modules, {"weasyprint": fake_weasy}):
            response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertTrue(response.content.startswith(b"%PDF"))
        fake_weasy.HTML.assert_called_once()
        call_kw = fake_weasy.HTML.call_args[1]
        self.assertIn("string", call_kw)
        html_str = call_kw["string"]
        self.assertIn("lang=", html_str)
        self.assertIn('scope="col">Description', html_str)
