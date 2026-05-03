"""Rail degradation + receipt reconciliation audit helpers."""

from __future__ import annotations

from decimal import Decimal

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase

from apps.accounts.models import User
from apps.academics.models import AcademicYear
from apps.compliance.models_audit import AuditLog
from apps.finance.models import (
    ComplianceProfile,
    Invoice,
    InvoiceLine,
    PaymentMethodCode,
    PaymentProofUpload,
)
from apps.finance.regional_payment_profiles import clear_profile_cache
from apps.finance.payment_fallback_engine import (
    MANUAL_FALLBACK_CODE,
    approve_payment_proof_reconciliation,
    assert_proof_matches_school,
    describe_pending_reconciliation,
    invoice_school_id,
    reject_payment_proof_reconciliation,
    select_effective_rail,
    select_primary_rail,
)
from apps.people.models import StudentProfile
from apps.schools.models import School


class PaymentFallbackEngineTests(TestCase):
    def tearDown(self):
        clear_profile_cache()

    def test_select_primary_rail_cm(self):
        self.assertEqual(select_primary_rail("CM"), "MTN_MOMO")

    def test_backup_selected_when_primary_unavailable(self):
        picked = select_effective_rail(
            "CM",
            {"MTN_MOMO": False, "ORANGE_MOMO": True},
        )
        self.assertEqual(picked["selected_rail"], "ORANGE_MOMO")

    def test_manual_fallback_when_all_online_rails_marked_down(self):
        picked = select_effective_rail(
            "GH",
            {
                "BANK": False,
                "CARD": False,
                "MTN_MOMO": False,
                "CASH": False,
            },
        )
        self.assertEqual(picked["selected_rail"], MANUAL_FALLBACK_CODE)
        self.assertEqual(picked["reason"], "all_listed_rails_unavailable_manual_path")

    def test_unknown_country_falls_back_safely(self):
        picked = select_effective_rail("ZZ", None)
        self.assertEqual(picked["selected_rail"], MANUAL_FALLBACK_CODE)
        self.assertEqual(picked["reason"], "unknown_country_manual_fallback")

    def _make_invoice_with_school(self, *, school: School, cc: str = "CM"):
        profile = ComplianceProfile.objects.create(
            name=f"P-{school.slug}",
            country_code=cc,
            currency_code="XAF" if cc == "CM" else "USD",
            is_active=True,
        )
        year = AcademicYear.objects.create(
            name="2026",
            start_date="2026-01-01",
            end_date="2026-12-31",
        )
        stu = StudentProfile.objects.create(
            first_name="T",
            last_name="U",
            student_code=f"STU-{school.slug}-{cc}",
            date_of_birth="2012-05-05",
            school=school,
            academic_year=year,
        )
        inv = Invoice.objects.create(
            school=school,
            profile=profile,
            academic_year=year,
            invoice_type=Invoice.InvoiceType.AR,
            status=Invoice.Status.ISSUED,
            student=stu,
            total_amount=Decimal("50.00"),
            balance_amount=Decimal("50.00"),
        )
        InvoiceLine.objects.create(
            invoice=inv,
            description="Fee",
            amount=Decimal("50.00"),
            unit_price=Decimal("50.00"),
        )
        return inv

    def test_offline_receipt_pending_describes_reconciliation(self):
        school = School.objects.create(
            name="Iso School",
            slug="iso-school",
            subdomain="iso",
            is_active=True,
        )
        inv = self._make_invoice_with_school(school=school)
        self.assertEqual(invoice_school_id(inv), school.pk)

        png_bytes = (
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\tpHYs\x00\x00\x0b\x13\x00\x00\x0b\x13\x01\x00\x9a\x9c\x18\x00\x00\x00\nIDATx\x9cc\xf8\x00\x00\x00\x01\x00\x01\x00\x00\x00\x00IEND\xaeB`\x82"
        )
        receipt = SimpleUploadedFile("stub.png", png_bytes, content_type="image/png")
        proof = PaymentProofUpload.objects.create(
            invoice=inv,
            uploaded_by=None,
            receipt_file=receipt,
            payment_method=PaymentMethodCode.CASH,
            uploaded_amount=Decimal("50.00"),
            verification_data={"amount": "50.00", "reference": "REF-1"},
            status=PaymentProofUpload.Status.PENDING,
        )
        desc = describe_pending_reconciliation(proof)
        self.assertTrue(desc["reconciliation_required"])
        self.assertEqual(desc["school_id"], school.pk)

    def test_reconciliation_approve_and_reject_write_audit_rows(self):
        school = School.objects.create(
            name="Audit School",
            slug="audit-school",
            subdomain="auditsc",
            is_active=True,
        )
        staff = User.objects.create_user(username="fin_staff", password="x")
        inv = self._make_invoice_with_school(school=school)

        png_bytes = (
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\tpHYs\x00\x00\x0b\x13\x00\x00\x0b\x13\x01\x00\x9a\x9c\x18\x00\x00\x00\nIDATx\x9cc\xf8\x00\x00\x00\x01\x00\x01\x00\x00\x00\x00IEND\xaeB`\x82"
        )
        receipt = SimpleUploadedFile("stub2.png", png_bytes, content_type="image/png")
        proof_ok = PaymentProofUpload.objects.create(
            invoice=inv,
            uploaded_by=staff,
            receipt_file=receipt,
            payment_method=PaymentMethodCode.CASH,
            uploaded_amount=Decimal("50.00"),
            verification_data={"amount": "50.00", "reference": "OK-1"},
            status=PaymentProofUpload.Status.PENDING,
        )
        receipt2 = SimpleUploadedFile("stub3.png", png_bytes, content_type="image/png")
        proof_bad = PaymentProofUpload.objects.create(
            invoice=inv,
            uploaded_by=staff,
            receipt_file=receipt2,
            payment_method=PaymentMethodCode.CASH,
            uploaded_amount=Decimal("1.00"),
            verification_data={"amount": "1.00"},
            status=PaymentProofUpload.Status.PENDING,
        )

        base = AuditLog.objects.count()
        approve_payment_proof_reconciliation(
            proof_ok,
            staff,
            expected_school_id=school.pk,
        )
        self.assertGreater(AuditLog.objects.count(), base)
        proof_ok.refresh_from_db()
        self.assertEqual(proof_ok.status, PaymentProofUpload.Status.VERIFIED)

        reject_payment_proof_reconciliation(
            proof_bad,
            staff,
            "Amount mismatch",
            expected_school_id=school.pk,
        )
        proof_bad.refresh_from_db()
        self.assertEqual(proof_bad.status, PaymentProofUpload.Status.REJECTED)
        self.assertTrue(
            AuditLog.objects.filter(
                model_name="PaymentProofUpload",
                action=AuditLog.Action.REJECT,
            )
            .filter(object_id=str(proof_bad.pk))
            .exists()
        )

    def test_tenant_isolation_blocks_cross_school_reconciliation(self):
        s1 = School.objects.create(name="S1", slug="s-one", subdomain="s1", is_active=True)
        s2 = School.objects.create(name="S2", slug="s-two", subdomain="s2", is_active=True)
        staff = User.objects.create_user(username="staff2", password="x")
        inv = self._make_invoice_with_school(school=s1)
        png_bytes = (
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\tpHYs\x00\x00\x0b\x13\x00\x00\x0b\x13\x01\x00\x9a\x9c\x18\x00\x00\x00\nIDATx\x9cc\xf8\x00\x00\x00\x01\x00\x01\x00\x00\x00\x00IEND\xaeB`\x82"
        )
        receipt = SimpleUploadedFile("stub4.png", png_bytes, content_type="image/png")
        proof = PaymentProofUpload.objects.create(
            invoice=inv,
            uploaded_by=staff,
            receipt_file=receipt,
            payment_method=PaymentMethodCode.CASH,
            uploaded_amount=Decimal("50.00"),
            verification_data={"amount": "50.00"},
            status=PaymentProofUpload.Status.PENDING,
        )
        with self.assertRaises(PermissionError):
            assert_proof_matches_school(proof, s2.pk)

        with self.assertRaises(PermissionError):
            approve_payment_proof_reconciliation(
                proof,
                staff,
                expected_school_id=s2.pk,
            )
