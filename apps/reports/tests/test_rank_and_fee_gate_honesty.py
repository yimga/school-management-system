"""Two honesty fixes on the report-card surface.

1. A student with no gradable marks was still handed a class rank ("8 / 20") on
   a report card whose subject table was empty and whose average was blank —
   they appear in the ranking aggregates because they are enrolled, so the
   position lookup happily returned an index.

2. The fee gate answered only yes/no, so a blocked parent saw "visit the
   Bursary" with no numbers. Schools here are paid in instalments and the gate
   releases at the enrollment-clearance threshold (50% by default), NOT at a
   zero balance — so the amount that actually unblocks a report card is usually
   far less than the outstanding balance. Saying so is the difference between
   "you owe 165,000" and "pay 82,500 to unblock".
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from django.test import TestCase

from apps.academics.models import (
    AcademicYear,
    Classroom,
    Department,
    Specialty,
    Term,
)
from apps.finance.models import ComplianceProfile, Invoice
from apps.people.models import StudentProfile
from apps.reports.services import (
    financial_clearance_block_message,
    financial_clearance_shortfall,
)
from apps.schools.models import School


class FeeGateShortfallTests(TestCase):
    """The 403 must name the balance AND the smaller amount that unblocks."""

    @classmethod
    def setUpTestData(cls):
        cls.school = School.objects.create(
            name="Buea Fee School",
            slug="buea-fee-school",
            subdomain="buea-fee-school",
            country_code="CM",
            is_active=True,
        )
        cls.year = AcademicYear.objects.create(
            school=cls.school,
            name="2025/2026",
            start_date=date(2025, 9, 1),
            end_date=date(2026, 7, 31),
            is_active=True,
        )
        dept = Department.objects.create(
            school=cls.school, name="General", code="GEN-FEE"
        )
        specialty = Specialty.objects.create(
            school=cls.school, department=dept, name="General", code="GENSPEC-FEE"
        )
        classroom = Classroom.objects.create(
            school=cls.school,
            academic_year=cls.year,
            department=dept,
            name="Form 1",
            code="F1-FEE",
        )
        cls.student = StudentProfile.objects.create(
            school=cls.school,
            first_name="Tabi",
            last_name="Ako",
            student_code="FEE-1",
            academic_year=cls.year,
            classroom=classroom,
            specialty=specialty,
            is_active=True,
        )
        cls.profile = ComplianceProfile.objects.create(
            name="Buea Fee", country_code="CM", currency_code="XAF"
        )
        cls.invoice = Invoice.objects.create(
            profile=cls.profile,
            school=cls.school,
            academic_year=cls.year,
            student=cls.student,
            reference="INV-FEE-1",
            invoice_type=Invoice.InvoiceType.AR,
            status=Invoice.Status.ISSUED,
            issued_date=date(2025, 9, 5),
            due_date=date(2025, 10, 5),
            total_amount=Decimal("165000.00"),
            balance_amount=Decimal("165000.00"),
        )

    def test_shortfall_reports_balance_and_clearance_gap(self):
        gap = financial_clearance_shortfall(self.student, self.year)
        self.assertEqual(gap["outstanding"], Decimal("165000.00"))
        # Default threshold is 50% of the invoice total.
        self.assertEqual(gap["needed_for_clearance"], Decimal("82500.00"))
        self.assertEqual(gap["invoices"], 1)

    def test_clearance_gap_never_exceeds_outstanding(self):
        gap = financial_clearance_shortfall(self.student, self.year)
        self.assertLessEqual(gap["needed_for_clearance"], gap["outstanding"])

    def test_message_states_both_numbers(self):
        msg = financial_clearance_block_message(self.student, self.year)
        self.assertIn("165000.00", msg)
        self.assertIn("82500.00", msg)
        self.assertIn("Bursary", msg)

    def test_message_falls_back_cleanly_when_nothing_outstanding(self):
        self.invoice.status = Invoice.Status.VOID
        self.invoice.save(update_fields=["status"])
        msg = financial_clearance_block_message(self.student, self.year)
        self.assertIn("Bursary", msg)
        self.assertNotIn("Outstanding balance", msg)

    def test_school_configured_threshold_is_honoured(self):
        self.school.settings = {"finance": {"enrollment_clearance_percent": 30}}
        self.school.save(update_fields=["settings"])
        self.student.refresh_from_db()
        gap = financial_clearance_shortfall(self.student, self.year)
        self.assertEqual(gap["needed_for_clearance"], Decimal("49500.00"))
