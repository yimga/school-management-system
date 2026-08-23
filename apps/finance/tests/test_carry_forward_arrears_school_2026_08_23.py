"""Year-rollover arrears invoices must carry the tenant.

``carry_forward_arrears`` was the ONLY AR invoice creator that omitted
``school`` from its ``get_or_create`` defaults (``create_fee_invoices`` sets it
explicitly). ``Invoice.school`` is nullable and ``Invoice.save()`` does no
backfill, so every "Opening balance / Arrears from <last year>" invoice landed
with school=NULL.

The rollover runs from ``accounts.views_rollover`` and ``accounts.tasks`` with
``carry_forward_arrears_on_rollover`` defaulting True, so the consequence was
routine: ``student_enrollment_blocked_for_unpaid`` filters
``Invoice.objects.filter(school=resolved_school, ...)``, so the NULL-school
arrears invoice was invisible and a student owing a full year of fees was NOT
blocked from re-enrolling or from their report card. ``record_provider_payment``
and ``reconcile_offline_payment_intent`` also guard on ``inv.school_id is not
None``, so a payment against that arrears invoice posted no fractional
clearance line either.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from apps.academics.models import AcademicYear
from apps.finance.fractional_ledger_services import (
    student_enrollment_blocked_for_unpaid,
)
from apps.finance.models import ComplianceProfile, Invoice, InvoiceLine
from apps.finance.services import carry_forward_arrears
from apps.people.models import StudentProfile
from apps.schools.models import School


class CarryForwardArrearsCarriesSchoolTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Rollover School",
            slug="rollover-mc",
            subdomain="rollover-mc",
            is_active=True,
        )
        self.profile = ComplianceProfile.objects.create(
            name="Rollover", country_code="CM", currency_code="XAF", is_active=True
        )
        self.source_year = AcademicYear.objects.create(
            name="2024/2025-roll",
            start_date=date(2024, 9, 1),
            end_date=date(2025, 6, 30),
        )
        self.target_year = AcademicYear.objects.create(
            name="2025/2026-roll",
            start_date=date(2025, 9, 1),
            end_date=date(2026, 6, 30),
        )
        self.student = StudentProfile.objects.create(
            school=self.school,
            first_name="Bih",
            last_name="Fomum",
            student_code="STU-ROLL-1",
            academic_year=self.source_year,
            is_active=True,
        )
        self.unpaid = Invoice.objects.create(
            profile=self.profile,
            school=self.school,
            student=self.student,
            academic_year=self.source_year,
            reference="INV-ROLL-OLD",
            invoice_type=Invoice.InvoiceType.AR,
            status=Invoice.Status.ISSUED,
            issued_date=timezone.localdate(),
            due_date=timezone.localdate(),
            total_amount=Decimal("750.00"),
            balance_amount=Decimal("750.00"),
        )
        InvoiceLine.objects.create(
            invoice=self.unpaid,
            description="Tuition",
            quantity=Decimal("1"),
            unit_price=Decimal("750.00"),
            amount=Decimal("750.00"),
        )

    def _arrears_invoice(self):
        return Invoice.objects.filter(
            academic_year=self.target_year,
            student=self.student,
            invoice_type=Invoice.InvoiceType.AR,
            reference=f"ARREARS-{self.target_year.name}-{self.student.student_code}",
        ).first()

    def test_arrears_invoice_is_created_with_the_students_school(self):
        created = carry_forward_arrears(self.source_year, self.target_year)
        # Vacuity guards: the rollover really produced the arrears row, for the
        # real outstanding amount -- not zero rows quietly.
        self.assertEqual(created, 1)
        arrears = self._arrears_invoice()
        self.assertIsNotNone(arrears)
        self.assertEqual(arrears.total_amount, Decimal("750.00"))

        self.assertEqual(
            arrears.school_id,
            self.school.pk,
            "an arrears invoice with school=NULL is invisible to every "
            "tenant-scoped enrollment / clearance query",
        )

    def test_unpaid_arrears_block_re_enrollment_in_the_new_year(self):
        # Vacuity guard: nothing blocks the student in the target year yet, so a
        # True below can only come from the arrears invoice this call creates.
        self.assertFalse(
            student_enrollment_blocked_for_unpaid(self.student, self.target_year)
        )

        carry_forward_arrears(self.source_year, self.target_year)

        self.assertTrue(
            student_enrollment_blocked_for_unpaid(self.student, self.target_year),
            "last year's unpaid fees must follow the student into the new year",
        )

    def test_rerunning_the_rollover_does_not_duplicate(self):
        self.assertEqual(carry_forward_arrears(self.source_year, self.target_year), 1)
        self.assertEqual(carry_forward_arrears(self.source_year, self.target_year), 0)
        self.assertEqual(
            Invoice.objects.filter(
                academic_year=self.target_year,
                student=self.student,
                invoice_type=Invoice.InvoiceType.AR,
            ).count(),
            1,
        )
