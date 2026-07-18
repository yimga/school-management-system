"""Admin "Approve receipts" must be able to approve manually-reviewed receipts.

Dead-guard backlog item 13 (re-audited). Two independent defects made the admin
approve action unable to approve anything:

1. ``school = getattr(queryset.select_related("school").first(), "school", None)``
   -- ``PaymentProofUpload`` has NO ``school`` FK, so ``select_related("school")``
   raised ``FieldError`` and 500'd the action (and reject) on the first row.
2. The loop filtered ``status=DISCREPANCY`` only. Schools running with
   ``finance_receipt_auto_verify_enabled=False`` upload receipts that stay
   ``PENDING`` ("It will be reviewed by finance staff") -- those could never be
   approved (Reject, by contrast, handled PENDING). Result for such schools:
   "Approved 0 receipt upload(s)" while nothing happened.

This test drives a PENDING receipt through ``approve_selected`` and asserts a
payment is created for it (payment creation is mocked to keep the fixture light).
"""
from __future__ import annotations

from decimal import Decimal
from unittest.mock import patch

from django.contrib import admin as django_admin
from django.test import RequestFactory, TestCase

from apps.academics.models import AcademicYear
from apps.accounts.models import User
from apps.finance.admin import PaymentProofUploadAdmin
from apps.finance.models import (
    ComplianceProfile,
    Invoice,
    PaymentMethodCode,
    PaymentProofUpload,
)
from apps.schools.models import School


class ApproveReceiptPendingActionTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(name="Test School", slug="tsc-appr")
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
        self.invoice = Invoice.objects.create(
            profile=self.profile,
            academic_year=self.year,
            invoice_type=Invoice.InvoiceType.AR,
            status=Invoice.Status.ISSUED,
            school=self.school,
            total_amount=Decimal("100.00"),
            balance_amount=Decimal("100.00"),
            issued_date="2026-02-01",
        )
        self.proof = PaymentProofUpload.objects.create(
            invoice=self.invoice,
            status=PaymentProofUpload.Status.PENDING,
            payment_method=PaymentMethodCode.CASH,
            receipt_file="finance/payment_proofs/t.pdf",
            verification_notes="paid in full at the cash office",
            verification_data={"amount": "100.00"},
        )
        self.user = User.objects.create_superuser(
            username="appr_admin", email="appr@example.com", password="Pass_1234"
        )
        self.model_admin = PaymentProofUploadAdmin(
            PaymentProofUpload, django_admin.site
        )
        # Sidestep the messages framework (no session wiring needed).
        self.model_admin.message_user = lambda *a, **k: None

    def _request(self):
        request = RequestFactory().post("/admin/finance/paymentproofupload/")
        request.user = self.user
        return request

    @patch("apps.finance.receipt_verification.ReceiptVerificationService")
    @patch("apps.finance.services.create_payment_from_receipt")
    def test_pending_receipt_is_approved(self, mock_create, mock_service):
        mock_create.return_value = object()
        queryset = PaymentProofUpload.objects.filter(pk=self.proof.pk)

        self.model_admin.approve_selected(self._request(), queryset)

        mock_create.assert_called_once()
        # The PENDING receipt (auto-verify-disabled manual-review workflow) was
        # the one handed to payment creation.
        approved = mock_create.call_args.args[0]
        self.assertEqual(approved.pk, self.proof.pk)

    @patch("apps.finance.receipt_verification.ReceiptVerificationService")
    @patch("apps.finance.services.create_payment_from_receipt")
    def test_already_verified_receipt_is_not_reprocessed(self, mock_create, mock_service):
        # Guard against double-crediting: VERIFIED rows stay out of the approve set.
        self.proof.status = PaymentProofUpload.Status.VERIFIED
        self.proof.save(update_fields=["status"])
        queryset = PaymentProofUpload.objects.filter(pk=self.proof.pk)

        self.model_admin.approve_selected(self._request(), queryset)

        mock_create.assert_not_called()
