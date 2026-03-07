from __future__ import annotations

from decimal import Decimal
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import User
from apps.academics.models import AcademicYear, Classroom, Department, Specialty
from apps.api.serializers import InvoiceSerializer
from apps.finance.models import ComplianceProfile, Invoice, PaymentMethodCode, PaymentProofUpload
from apps.people.models import StudentProfile


class ReceiptUploadFlowTests(TestCase):
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
            first_name="Abajo",
            last_name="Jeffter",
            student_code="STU-001",
            academic_year=self.year,
            classroom=self.classroom,
            specialty=self.specialty,
        )
        self.user = User.objects.create_superuser(
            username="superadmin",
            password="Pass_1234",
            email="superadmin@example.com",
        )
        self.invoice = Invoice.objects.create(
            profile=self.profile,
            academic_year=self.year,
            invoice_type=Invoice.InvoiceType.AR,
            status=Invoice.Status.ISSUED,
            student=self.student,
            total_amount=Decimal("25000.00"),
            balance_amount=Decimal("25000.00"),
            issued_date="2026-02-01",
        )
        self.client.login(username="superadmin", password="Pass_1234")

    def test_invoice_detail_receipt_form_has_idempotency_fields_and_momo_options(self):
        response = self.client.get(reverse("finance:invoice_detail", args=[self.invoice.id]))
        self.assertContains(response, 'id="receipt-upload-form"')
        self.assertContains(response, 'id="idempotency_key"')
        self.assertContains(response, 'value="MTN_MOMO"')
        self.assertContains(response, 'value="ORANGE_MOMO"')

    @patch("apps.finance.tasks.process_payment_receipt_upload_task.delay")
    @patch("apps.finance.views.ReceiptFraudDetector.detect_fraud")
    def test_upload_receipt_captures_idempotency_and_request_metadata(self, mock_detect, mock_delay):
        mock_detect.return_value = {
            "fraud_risk_score": 8,
            "fraud_flags": [],
            "file_hash": "abc123hash",
            "recommendation": "approve",
        }
        receipt = SimpleUploadedFile(
            "receipt.png",
            b"fake-image-data",
            content_type="image/png",
        )
        response = self.client.post(
            reverse("finance:upload_payment_receipt", args=[self.invoice.id]),
            data={
                "receipt_file": receipt,
                "payment_method": PaymentMethodCode.MTN_MOMO,
                "uploaded_amount": "25000",
                "transaction_reference": "MTN-REF-1",
                "idempotency_key": "test-idempo-1",
            },
            HTTP_USER_AGENT="TestBrowser/1.0",
            REMOTE_ADDR="127.0.0.99",
        )
        self.assertEqual(response.status_code, 302)
        upload = PaymentProofUpload.objects.get(invoice=self.invoice)
        self.assertEqual(upload.idempotency_key, "test-idempo-1")
        self.assertEqual(str(upload.ip_address), "127.0.0.99")
        self.assertEqual(upload.user_agent, "TestBrowser/1.0")
        mock_delay.assert_called_once()

    def test_invoice_serializer_matches_current_invoice_model_fields(self):
        data = InvoiceSerializer(instance=self.invoice).data
        self.assertIn("total_amount", data)
        self.assertIn("issued_date", data)
        self.assertIn("payment_code", data)
        self.assertNotIn("amount", data)
        self.assertNotIn("invoice_date", data)
        self.assertNotIn("description", data)
