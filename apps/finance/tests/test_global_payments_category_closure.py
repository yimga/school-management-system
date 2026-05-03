"""
Global payments category closure — profiles, fallback chain, reconciliation audit, isolation.
"""

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
    PaymentRail,
    RegionPaymentProfile,
    TenantPaymentPolicy,
)
from apps.finance.payment_fallback_engine import (
    approve_payment_proof_reconciliation,
    coerce_verification_amount_dict,
    reject_payment_proof_reconciliation,
    select_effective_rail,
)
from apps.finance.payment_gateway_health import (
    GatewayHealthStatus,
    build_gateway_health_rows,
    default_rail_health_check,
)
from apps.finance.regional_payment_profiles import (
    clear_profile_cache,
    get_normalized_regional_profile,
    list_supported_country_codes,
    normalize_regional_profile_row,
)
from apps.people.models import StudentProfile
from apps.schools.models import School


class GlobalPaymentsCategoryClosureTests(TestCase):
    REQUIRED_CC = ("CM", "GH", "NG", "KE", "US", "GB", "EU")

    def tearDown(self):
        clear_profile_cache()

    def test_all_required_country_profiles_resolve_with_metadata(self):
        for cc in self.REQUIRED_CC:
            norm = get_normalized_regional_profile(cc)
            self.assertIsNotNone(norm, msg=cc)
            self.assertEqual(norm.get("country_code"), cc)
            self.assertTrue(norm.get("primary_rail"))
            self.assertTrue(norm.get("backup_rail"))
            self.assertIn("manual_fallback", norm)
            self.assertIn("offline_receipt_allowed", norm)
            self.assertIn("reconciliation_required", norm)
            self.assertTrue(norm.get("tenant_setup_steps"))
            self.assertTrue(norm.get("operator_ready_label"))
            self.assertEqual(norm.get("provider_setup_status"), "external_required")

    def test_normalize_missing_credentials_safe(self):
        norm = normalize_regional_profile_row(None)
        self.assertIsNone(norm)
        out = default_rail_health_check(
            "CARD",
            {"provider_setup_status": "external_required", "provider_notes": ""},
            None,
            None,
        )
        self.assertEqual(out["status"], GatewayHealthStatus.EXTERNAL_REQUIRED)

    def test_primary_ready_effective_rail(self):
        eff = select_effective_rail(
            "NG",
            {"BANK": True, "CARD": False, "CASH": False},
        )
        self.assertEqual(eff.get("reason"), "primary")

    def test_offline_receipt_creates_reconciliation_and_audit(self):
        """Approve/reject reconciliation writes audit (tenant isolation on approve)."""
        school = School.objects.create(
            name="Reco School",
            slug="reco-s",
            subdomain="recosch",
            is_active=True,
        )
        primary = PaymentRail.objects.create(
            code="ng-bank-closure",
            label="Bank",
            kind=PaymentRail.RailKind.BANK_TRANSFER,
        )
        backup = PaymentRail.objects.create(
            code="ng-card-closure",
            label="Card",
            kind=PaymentRail.RailKind.CARD,
        )
        region = RegionPaymentProfile.objects.create(
            country_code="NG",
            name="Nigeria",
            primary_rail=primary,
            backup_rail=backup,
        )
        TenantPaymentPolicy.objects.create(
            school=school,
            region_profile=region,
            allow_manual_offline_proof=True,
        )
        profile = ComplianceProfile.objects.create(
            name="NG",
            country_code="NG",
            currency_code="NGN",
            is_active=True,
        )
        year = AcademicYear.objects.create(
            name="2026",
            start_date="2026-01-01",
            end_date="2026-12-31",
        )
        student = StudentProfile.objects.create(
            first_name="A",
            last_name="B",
            student_code="S1",
            date_of_birth="2012-01-15",
            academic_year=year,
            school=school,
        )
        invoice = Invoice.objects.create(
            profile=profile,
            academic_year=year,
            invoice_type=Invoice.InvoiceType.AR,
            status=Invoice.Status.ISSUED,
            student=student,
            school=school,
            total_amount=Decimal("100.00"),
            balance_amount=Decimal("100.00"),
            issued_date="2026-03-01",
        )
        InvoiceLine.objects.create(
            invoice=invoice,
            description="Fee",
            unit_price=Decimal("100.00"),
            amount=Decimal("100.00"),
        )
        staff = User.objects.create_user(
            username="bursar",
            password="Pass_1234",
            email="b@example.com",
            is_staff=True,
        )
        png_bytes = (
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02"
            b"\x00\x00\x00\x90wS\xde\x00\x00\x00\tpHYs\x00\x00\x0b\x13\x00\x00\x0b\x13"
            b"\x01\x00\x9a\x9c\x18\x00\x00\x00\nIDATx\x9cc\xf8\x00\x00\x00\x01\x00\x01"
            b"\x00\x00\x00\x00IEND\xaeB`\x82"
        )
        receipt = SimpleUploadedFile("r.png", png_bytes, content_type="image/png")
        proof = PaymentProofUpload.objects.create(
            invoice=invoice,
            uploaded_by=staff,
            receipt_file=receipt,
            payment_method=PaymentMethodCode.CASH,
            uploaded_amount=Decimal("100.00"),
            verification_data={"amount": "100.00", "reference": "R1"},
            status=PaymentProofUpload.Status.PENDING,
        )
        approve_payment_proof_reconciliation(
            proof,
            staff,
            receipt_data=coerce_verification_amount_dict(proof),
            expected_school_id=school.pk,
        )
        self.assertTrue(
            AuditLog.objects.filter(
                model_name="PaymentProofUpload",
                action=AuditLog.Action.APPROVE,
            ).exists()
        )

        receipt2 = SimpleUploadedFile("r2.png", png_bytes, content_type="image/png")
        proof2 = PaymentProofUpload.objects.create(
            invoice=invoice,
            uploaded_by=staff,
            receipt_file=receipt2,
            payment_method=PaymentMethodCode.CASH,
            uploaded_amount=Decimal("10.00"),
            verification_data={"amount": "10.00"},
            status=PaymentProofUpload.Status.PENDING,
        )
        reject_payment_proof_reconciliation(
            proof2,
            staff,
            "no match",
            expected_school_id=school.pk,
        )
        self.assertTrue(
            AuditLog.objects.filter(
                model_name="PaymentProofUpload",
                action=AuditLog.Action.REJECT,
            ).exists()
        )

    def test_tenant_mismatch_on_reconcile_raises(self):
        school = School.objects.create(
            name="S1",
            slug="s1",
            subdomain="s1x",
            is_active=True,
        )
        other = School.objects.create(
            name="S2",
            slug="s2",
            subdomain="s2x",
            is_active=True,
        )
        profile = ComplianceProfile.objects.create(
            name="NG",
            country_code="NG",
            currency_code="NGN",
            is_active=True,
        )
        year = AcademicYear.objects.create(
            name="2026",
            start_date="2026-01-01",
            end_date="2026-12-31",
        )
        student = StudentProfile.objects.create(
            first_name="A",
            last_name="B",
            student_code="S2",
            date_of_birth="2011-02-02",
            academic_year=year,
            school=school,
        )
        invoice = Invoice.objects.create(
            profile=profile,
            academic_year=year,
            invoice_type=Invoice.InvoiceType.AR,
            status=Invoice.Status.ISSUED,
            student=student,
            school=school,
            total_amount=Decimal("50.00"),
            balance_amount=Decimal("50.00"),
            issued_date="2026-03-01",
        )
        InvoiceLine.objects.create(
            invoice=invoice,
            description="Fee",
            unit_price=Decimal("50.00"),
            amount=Decimal("50.00"),
        )
        png_bytes = (
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02"
            b"\x00\x00\x00\x90wS\xde\x00\x00\x00\tpHYs\x00\x00\x0b\x13\x00\x00\x0b\x13"
            b"\x01\x00\x9a\x9c\x18\x00\x00\x00\nIDATx\x9cc\xf8\x00\x00\x00\x01\x00\x01"
            b"\x00\x00\x00\x00IEND\xaeB`\x82"
        )
        receipt = SimpleUploadedFile("r3.png", png_bytes, content_type="image/png")
        proof = PaymentProofUpload.objects.create(
            invoice=invoice,
            uploaded_amount=Decimal("50.00"),
            receipt_file=receipt,
            payment_method=PaymentMethodCode.CASH,
            verification_data={"amount": "50.00"},
            status=PaymentProofUpload.Status.PENDING,
        )
        staff = User.objects.create_user(
            username="x",
            password="Pass_1234",
            email="x@example.com",
            is_staff=True,
        )
        with self.assertRaises(PermissionError):
            approve_payment_proof_reconciliation(
                proof,
                staff,
                receipt_data=coerce_verification_amount_dict(proof),
                expected_school_id=other.pk,
            )

    def test_supported_catalog_includes_all_required(self):
        codes = list_supported_country_codes()
        for cc in self.REQUIRED_CC:
            self.assertIn(cc, codes)

    def test_health_rows_include_primary_backup_manual(self):
        school = School.objects.create(
            name="H",
            slug="h",
            subdomain="hsch",
            is_active=True,
        )
        cp = ComplianceProfile.objects.create(
            name="GH",
            country_code="GH",
            currency_code="GHS",
            is_active=True,
        )
        rows = build_gateway_health_rows(school, cp)
        roles = {r.get("role") for r in rows}
        self.assertIn("primary", roles)
        self.assertIn("backup", roles)
        self.assertIn("manual_fallback", roles)
