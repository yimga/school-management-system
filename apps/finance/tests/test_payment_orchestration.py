"""Regional payment rails, tenant policy, and simple UX flow builder."""

from __future__ import annotations

from decimal import Decimal

from django.test import TestCase

from apps.finance.models import (
    ComplianceProfile,
    Invoice,
    InvoiceLine,
    OfflinePaymentIntent,
    PaymentMethodCode,
    PaymentRail,
    RegionPaymentProfile,
    TenantPaymentPolicy,
)
from apps.finance.payment_orchestration import build_simple_payment_flow
from apps.academics.models import AcademicYear
from apps.people.models import StudentProfile
from apps.schools.models import School


class RegionPaymentFallbackMatrixTests(TestCase):
    """DB + policy contract: distinct rails per region; manual fallback reflects policy."""

    def test_all_persisted_region_profiles_have_distinct_primary_and_backup(self):
        for rp in RegionPaymentProfile.objects.all():
            self.assertIsNotNone(rp.primary_rail_id)
            self.assertIsNotNone(rp.backup_rail_id)
            self.assertNotEqual(
                rp.primary_rail_id,
                rp.backup_rail_id,
                msg=f"{rp.country_code}: primary and backup rails must differ",
            )

    def test_build_simple_payment_flow_manual_fallback_follows_policy_flag(self):
        school_a = School.objects.create(
            name="Manual on",
            slug="manual-on",
            subdomain="manualon",
            is_active=True,
        )
        school_b = School.objects.create(
            name="Manual off",
            slug="manual-off",
            subdomain="manualoff",
            is_active=True,
        )
        r1 = PaymentRail.objects.create(
            code="zx-a", label="ZX A", kind=PaymentRail.RailKind.BANK_TRANSFER
        )
        r2 = PaymentRail.objects.create(
            code="zx-b", label="ZX B", kind=PaymentRail.RailKind.BANK_TRANSFER
        )
        region = RegionPaymentProfile.objects.create(
            country_code="ZX",
            name="ZX test region",
            primary_rail=r1,
            backup_rail=r2,
        )
        pol_on = TenantPaymentPolicy.objects.create(
            school=school_a,
            region_profile=region,
            allow_manual_offline_proof=True,
        )
        pol_off = TenantPaymentPolicy.objects.create(
            school=school_b,
            region_profile=region,
            allow_manual_offline_proof=False,
        )
        self.assertTrue(build_simple_payment_flow(pol_on)["allow_manual_offline_proof"])
        self.assertFalse(build_simple_payment_flow(pol_off)["allow_manual_offline_proof"])
        self.assertEqual(len(build_simple_payment_flow(pol_on)["choices"]), 2)


class PaymentOrchestrationTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Global Test School",
            slug="global-test-school",
            subdomain="globaltest",
            is_active=True,
        )
        self.primary = PaymentRail.objects.create(
            code="cm-mtn",
            label="MTN MoMo",
            kind=PaymentRail.RailKind.MOBILE_MONEY,
        )
        self.backup = PaymentRail.objects.create(
            code="cm-orange",
            label="Orange Money",
            kind=PaymentRail.RailKind.MOBILE_MONEY,
        )
        self.region = RegionPaymentProfile.objects.create(
            country_code="CM",
            name="Cameroon default",
            primary_rail=self.primary,
            backup_rail=self.backup,
        )
        self.policy = TenantPaymentPolicy.objects.create(
            school=self.school,
            region_profile=self.region,
        )

    def test_region_profile_requires_primary_and_backup(self):
        self.assertEqual(self.region.primary_rail_id, self.primary.id)
        self.assertEqual(self.region.backup_rail_id, self.backup.id)

    def test_build_simple_payment_flow_two_choices(self):
        flow = build_simple_payment_flow(self.policy)
        self.assertEqual(len(flow["choices"]), 2)
        roles = {c["role"] for c in flow["choices"]}
        self.assertEqual(roles, {"PRIMARY", "BACKUP"})
        self.assertEqual(len(flow["steps"]), 3)

    def test_offline_payment_intent_model_exists_for_queue(self):
        """Smoke: intent links invoice for reconciliation queue."""
        profile = ComplianceProfile.objects.create(
            name="P",
            country_code="CM",
        )
        year = AcademicYear.objects.create(
            name="2025",
            start_date="2025-01-01",
            end_date="2025-12-31",
        )
        stu = StudentProfile.objects.create(
            first_name="A",
            last_name="B",
            date_of_birth="2012-01-01",
        )
        inv = Invoice.objects.create(
            profile=profile,
            academic_year=year,
            invoice_type=Invoice.InvoiceType.AR,
            status=Invoice.Status.ISSUED,
            student=stu,
            total_amount=Decimal("10.00"),
            balance_amount=Decimal("10.00"),
        )
        intent = OfflinePaymentIntent.objects.create(
            invoice=inv,
            amount=Decimal("10.00"),
            payment_method=PaymentMethodCode.CASH,
            client_offline_id="e2e-1",
        )
        self.assertEqual(intent.status, OfflinePaymentIntent.Status.QUEUED_REVIEW)

    def test_reconcile_offline_intent_creates_payment(self):
        from apps.accounts.models import User
        from apps.finance.models import Payment
        from apps.finance.payment_orchestration import reconcile_offline_payment_intent

        staff = User.objects.create_user(username="recon_staff_1", password="x")
        profile = ComplianceProfile.objects.create(
            name="Recon region",
            country_code="CM",
            available_payment_methods=["CASH", "BANK"],
        )
        year = AcademicYear.objects.create(
            name="Y1",
            start_date="2025-01-01",
            end_date="2025-12-31",
        )
        stu = StudentProfile.objects.create(
            first_name="X",
            last_name="Y",
            date_of_birth="2011-01-01",
        )
        inv = Invoice.objects.create(
            profile=profile,
            academic_year=year,
            invoice_type=Invoice.InvoiceType.AR,
            status=Invoice.Status.ISSUED,
            student=stu,
            total_amount=Decimal("100.00"),
            balance_amount=Decimal("100.00"),
        )
        # Lines drive recalculate_invoice on payment save; without them total becomes 0 and validation fails.
        InvoiceLine.objects.create(
            invoice=inv,
            description="Fee",
            amount=Decimal("100.00"),
            unit_price=Decimal("100.00"),
        )
        intent = OfflinePaymentIntent.objects.create(
            invoice=inv,
            amount=Decimal("40.00"),
            payment_method=PaymentMethodCode.CASH,
        )
        payment = reconcile_offline_payment_intent(intent, reconciled_by=staff)
        self.assertTrue(Payment.objects.filter(pk=payment.pk).exists())
        intent.refresh_from_db()
        inv.refresh_from_db()
        self.assertEqual(intent.status, OfflinePaymentIntent.Status.RECONCILED)
        self.assertLessEqual(inv.balance_amount, inv.total_amount)
