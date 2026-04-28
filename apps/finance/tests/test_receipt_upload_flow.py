from __future__ import annotations

from decimal import Decimal
import uuid
from unittest.mock import patch
from types import SimpleNamespace

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import User
from apps.academics.models import AcademicYear, Classroom, Department, Specialty
from apps.api.serializers import InvoiceSerializer
from apps.finance.models import (
    ComplianceProfile,
    Invoice,
    PaymentMethodCode,
    PaymentProofUpload,
)
from apps.people.models import StudentProfile


def _finance_site_namespace(profile: ComplianceProfile) -> SimpleNamespace:
    return SimpleNamespace(
        compliance_profile=profile,
        get_finance_runtime_config=lambda: {
            "receipt_upload_enabled": True,
            "receipt_auto_verify_enabled": True,
            "receipt_max_size_mb": 10,
            "receipt_allowed_extensions": "png,jpg,jpeg,pdf",
            "receipt_idempotency_window_minutes": 15,
        },
        finance_receipt_upload_enabled=True,
        finance_receipt_max_size_mb=10,
        finance_receipt_allowed_extensions="png,jpg,jpeg,pdf",
        finance_receipt_idempotency_window_minutes=15,
        finance_receipt_auto_verify_enabled=True,
    )


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
        response = self.client.get(
            reverse("finance:invoice_detail", args=[self.invoice.id])
        )
        self.assertContains(response, 'id="receipt-upload-form"')
        self.assertContains(response, 'id="idempotency_key"')
        self.assertContains(response, 'value="MTN_MOMO"')
        self.assertContains(response, 'value="ORANGE_MOMO"')

    @patch("apps.finance.tasks.process_payment_receipt_upload_task.delay")
    @patch("apps.finance.fraud_detection.ReceiptFraudDetector.detect_fraud")
    def test_upload_receipt_captures_idempotency_and_request_metadata(
        self, mock_detect, mock_delay
    ):
        file_hash = f"abc123hash-{uuid.uuid4().hex}"
        mock_detect.return_value = {
            "fraud_risk_score": 8,
            "fraud_flags": [],
            "file_hash": file_hash,
            "recommendation": "approve",
        }
        receipt = SimpleUploadedFile(
            "receipt.png",
            b"fake-image-data",
            content_type="image/png",
        )
        site_ns = _finance_site_namespace(self.profile)
        with (
            patch(
                "apps.finance.views_common.get_effective_site_settings",
                return_value=site_ns,
            ),
            patch(
                "apps.finance.views_invoicing.get_effective_site_settings",
                return_value=site_ns,
            ),
        ):
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

    @patch("apps.finance.tasks.process_payment_receipt_upload_task.delay")
    @patch("apps.finance.fraud_detection.ReceiptFraudDetector.detect_fraud")
    @patch("apps.finance.views_invoicing.get_effective_site_settings")
    def test_upload_receipt_uses_owner_scoped_finance_policy(
        self,
        mock_get_effective_site_settings,
        mock_detect,
        mock_delay,
    ):
        owner_hash = f"owner-policy-hash-{uuid.uuid4().hex}"
        mock_detect.return_value = {
            "fraud_risk_score": 8,
            "fraud_flags": [],
            "file_hash": owner_hash,
            "recommendation": "approve",
        }
        receipt = SimpleUploadedFile(
            "receipt.png",
            b"fake-image-data",
            content_type="image/png",
        )

        site_ns = SimpleNamespace(
            compliance_profile=self.profile,
            get_finance_runtime_config=lambda: {
                "receipt_upload_enabled": True,
                "receipt_auto_verify_enabled": False,
                "receipt_max_size_mb": 10,
                "receipt_allowed_extensions": "png,jpg,jpeg,pdf",
                "receipt_idempotency_window_minutes": 15,
            },
            finance_receipt_upload_enabled=True,
            finance_receipt_max_size_mb=10,
            finance_receipt_allowed_extensions="png,jpg,jpeg,pdf",
            finance_receipt_idempotency_window_minutes=15,
            finance_receipt_auto_verify_enabled=False,
        )
        mock_get_effective_site_settings.return_value = site_ns
        with patch(
            "apps.finance.views_common.get_effective_site_settings",
            return_value=site_ns,
        ):
            response = self.client.post(
                reverse("finance:upload_payment_receipt", args=[self.invoice.id]),
                data={
                    "receipt_file": receipt,
                    "payment_method": PaymentMethodCode.MTN_MOMO,
                    "uploaded_amount": "25000",
                    "transaction_reference": "MTN-OWNER-REF-1",
                    "idempotency_key": "owner-finance-policy-1",
                },
            )

        self.assertEqual(response.status_code, 302)
        upload = PaymentProofUpload.objects.get(
            invoice=self.invoice, file_hash=owner_hash
        )
        self.assertEqual(upload.idempotency_key, "owner-finance-policy-1")
        mock_delay.assert_not_called()

    def test_invoice_serializer_matches_current_invoice_model_fields(self):
        data = InvoiceSerializer(instance=self.invoice).data
        self.assertIn("total_amount", data)
        self.assertIn("issued_date", data)
        self.assertIn("payment_code", data)
        self.assertNotIn("amount", data)
        self.assertNotIn("invoice_date", data)
        self.assertNotIn("description", data)
