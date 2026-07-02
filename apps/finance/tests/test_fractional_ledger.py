"""Fractional payment ledger — partial posts and enrollment clearance."""

from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from apps.academics.models import AcademicYear
from apps.finance.fractional_ledger_services import (
    enrollment_clearance_for_invoice,
    post_partial_payment,
    student_enrollment_blocked_for_unpaid,
)
from apps.finance.models import ComplianceProfile, Invoice, InvoiceLine
from apps.finance.models_fractional_ledger import FractionalPaymentLedger
from apps.people.models import StudentProfile
from apps.platform_runtime.helpers import get_platform_site_settings_record
from apps.reports.services import student_has_financial_clearance
from apps.schools.models import School


class FractionalLedgerTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(name="Ledger School", is_active=True)
        self.profile = ComplianceProfile.objects.create(name="Ledger", country_code="CM")
        self.year = AcademicYear.objects.create(
            name="2025/2026",
            start_date="2025-09-01",
            end_date="2026-06-30",
            is_active=True,
        )
        self.invoice = Invoice.objects.create(
            profile=self.profile,
            school=self.school,
            academic_year=self.year,
            reference="INV-FRAC-001",
            invoice_type=Invoice.InvoiceType.AR,
            status=Invoice.Status.ISSUED,
            issued_date=timezone.localdate(),
            due_date=timezone.localdate(),
            total_amount=Decimal("1000.00"),
            balance_amount=Decimal("1000.00"),
        )
        InvoiceLine.objects.create(
            invoice=self.invoice,
            description="Tuition",
            quantity=Decimal("1"),
            unit_price=Decimal("1000.00"),
            amount=Decimal("1000.00"),
        )

    def test_three_partial_posts_converge_and_idempotent(self):
        post_partial_payment(
            school=self.school,
            invoice=self.invoice,
            amount=Decimal("200.00"),
            idempotency_key="cash-1",
        )
        r2 = post_partial_payment(
            school=self.school,
            invoice=self.invoice,
            amount=Decimal("300.00"),
            idempotency_key="cash-2",
        )
        r3 = post_partial_payment(
            school=self.school,
            invoice=self.invoice,
            amount=Decimal("500.00"),
            idempotency_key="cash-3",
        )
        dup = post_partial_payment(
            school=self.school,
            invoice=self.invoice,
            amount=Decimal("999.00"),
            idempotency_key="cash-2",
        )
        self.assertEqual(r2.pk, dup.pk)
        self.assertEqual(r3.running_paid_total, Decimal("1000.00"))
        self.assertEqual(r3.invoice_balance_after, Decimal("0.00"))
        self.assertTrue(r3.enrollment_clearance_met)
        self.assertEqual(
            FractionalPaymentLedger.objects.filter(invoice=self.invoice).count(), 3
        )

    def test_clearance_helper_matches_ledger(self):
        post_partial_payment(
            school=self.school,
            invoice=self.invoice,
            amount=Decimal("600.00"),
            idempotency_key="half-plus",
        )
        self.assertTrue(enrollment_clearance_for_invoice(self.invoice, school=self.school))


class FractionalEnrollmentGatingTests(TestCase):
    """The headline micro-finance loop: partial posts gate enrollment / results.

    Proves the clearance signal is actually CONSUMED — both by the new public
    gate ``student_enrollment_blocked_for_unpaid`` and by the live
    ``reports.services.student_has_financial_clearance`` enforcement helper
    (the one wired into the 6 report-card/transcript views + year-close).
    """

    def setUp(self):
        # School.slug/subdomain are unique WITHOUT auto-derivation; creating two
        # schools with the blank defaults collides on the second insert (both get
        # ""), so distinct values are required — same pattern as
        # test_payment_fallback_engine.
        self.school = School.objects.create(
            name="Gate School", slug="gate-school", subdomain="gate-school", is_active=True
        )
        self.other_school = School.objects.create(
            name="Other Tenant", slug="gate-other", subdomain="gate-other", is_active=True
        )
        self.profile = ComplianceProfile.objects.create(name="Gate", country_code="CM")
        self.year = AcademicYear.objects.create(
            name="2025/2026",
            start_date="2025-09-01",
            end_date="2026-06-30",
            is_active=True,
        )
        self.student = StudentProfile.objects.create(
            school=self.school,
            first_name="Ama",
            last_name="Mensah",
            student_code="STU-GATE-1",
            academic_year=self.year,
            is_active=True,
        )
        self.invoice = Invoice.objects.create(
            profile=self.profile,
            school=self.school,
            student=self.student,
            academic_year=self.year,
            reference="INV-GATE-001",
            invoice_type=Invoice.InvoiceType.AR,
            status=Invoice.Status.ISSUED,
            issued_date=timezone.localdate(),
            due_date=timezone.localdate(),
            total_amount=Decimal("1000.00"),
            balance_amount=Decimal("1000.00"),
        )
        InvoiceLine.objects.create(
            invoice=self.invoice,
            description="Tuition",
            quantity=Decimal("1"),
            unit_price=Decimal("1000.00"),
            amount=Decimal("1000.00"),
        )
        # Turn the gate ON (flag defaults True, but be explicit for the test).
        site = get_platform_site_settings_record(create=True)
        site.apply_feature_control_state(
            field_updates={
                "backend_feature_flags": {
                    "block_report_download_if_outstanding_balance": True,
                },
            },
        )

    def test_no_payment_blocks_enrollment_and_results(self):
        # Nothing paid on the regular OR fractional ledger -> blocked.
        self.assertTrue(
            student_enrollment_blocked_for_unpaid(
                self.student, self.year, school=self.school
            )
        )
        self.assertFalse(
            student_has_financial_clearance(self.student, self.year)
        )

    def test_partial_below_threshold_still_blocks(self):
        # 200 of 1000 = 20%, below the default 50% clearance threshold.
        post_partial_payment(
            school=self.school,
            invoice=self.invoice,
            amount=Decimal("200.00"),
            student=self.student,
            idempotency_key="gate-cash-1",
        )
        self.assertTrue(
            student_enrollment_blocked_for_unpaid(
                self.student, self.year, school=self.school
            )
        )
        self.assertFalse(
            student_has_financial_clearance(self.student, self.year)
        )

    def test_partial_reaching_threshold_clears(self):
        # 600 of 1000 = 60%, meets the default 50% threshold even though the
        # regular Payment ledger (computed_balance) still shows 1000 owing.
        post_partial_payment(
            school=self.school,
            invoice=self.invoice,
            amount=Decimal("600.00"),
            student=self.student,
            idempotency_key="gate-cash-2",
        )
        self.assertGreater(self.invoice.computed_balance, Decimal("0.00"))
        self.assertFalse(
            student_enrollment_blocked_for_unpaid(
                self.student, self.year, school=self.school
            )
        )
        self.assertTrue(
            student_has_financial_clearance(self.student, self.year)
        )

    def test_custom_tenant_threshold_percent_respected(self):
        # Tenant raises the bar to 80%; 600/1000 = 60% no longer clears.
        self.school.settings = {"finance": {"enrollment_clearance_percent": 80}}
        self.school.save(update_fields=["settings"])
        post_partial_payment(
            school=self.school,
            invoice=self.invoice,
            amount=Decimal("600.00"),
            student=self.student,
            idempotency_key="gate-cash-3",
        )
        self.assertTrue(
            student_enrollment_blocked_for_unpaid(
                self.student, self.year, school=self.school
            )
        )

    def test_gate_is_tenant_scoped(self):
        # A fractional post booked under another tenant must NOT clear this
        # student's invoice (the ledger lookup is school-scoped).
        post_partial_payment(
            school=self.other_school,
            invoice=self.invoice,
            amount=Decimal("600.00"),
            student=self.student,
            idempotency_key="cross-tenant-leak",
        )
        # Booked under other_school -> this school's clearance is unaffected.
        self.assertTrue(
            student_enrollment_blocked_for_unpaid(
                self.student, self.year, school=self.school
            )
        )
        # And a query scoped to the wrong tenant sees no invoice for this
        # student at all -> reports no block (no leak in either direction).
        self.assertFalse(
            student_enrollment_blocked_for_unpaid(
                self.student, self.year, school=self.other_school
            )
        )
