"""student360 finance rollup must exclude VOID invoices — matching the finance SOT.

The 360 headline "Invoice total"/"Invoices" summed EVERY invoice regardless of
status, but a voided invoice still carries a positive ``total_amount`` and the
authoritative finance balance runner
(``finance/family_billing_aggregator.py::_default_balance_runner``) excludes VOID.
So a student with a voided invoice saw an overstated total that diverged from the
finance system-of-record.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from django.test import TestCase

from apps.academics.models import AcademicYear, Classroom, Department, Specialty
from apps.finance.models import ComplianceProfile, Invoice
from apps.people.models import StudentProfile
from apps.schools.models import School
from apps.student360.services import get_student_360_summary


class Student360InvoiceVoidExclusionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        uid = uuid.uuid4().hex[:8]
        cls.school = School.objects.create(
            name=f"S360 {uid}", slug=f"s360-{uid}", subdomain=f"s360-{uid}"
        )
        cls.year = AcademicYear.objects.create(
            name=f"2025/2026-{uid}",
            start_date=date(2025, 9, 1),
            end_date=date(2026, 6, 30),
            school=cls.school,
        )
        cls.dept = Department.objects.create(school=cls.school, name="Gen", code=f"G-{uid}")
        cls.spec = Specialty.objects.create(
            school=cls.school, department=cls.dept, name="Gen", code=f"GS-{uid}"
        )
        cls.classroom = Classroom.objects.create(
            school=cls.school,
            academic_year=cls.year,
            department=cls.dept,
            name="Form 1",
            code=f"F1-{uid}",
        )
        cls.profile = ComplianceProfile.objects.create(name=f"CP {uid}", country_code="CM")
        cls.student = StudentProfile.objects.create(
            school=cls.school,
            first_name="Jae",
            last_name="Learner",
            student_code=f"STD-{uid}",
            admission_number=f"ADM-{uid}",
            academic_year=cls.year,
            classroom=cls.classroom,
            specialty=cls.spec,
        )

        def inv(amount, status):
            return Invoice.objects.create(
                profile=cls.profile,
                academic_year=cls.year,
                student=cls.student,
                total_amount=Decimal(amount),
                balance_amount=Decimal(amount),
                status=status,
            )

        cls.live = inv("100.00", Invoice.Status.ISSUED)
        cls.voided = inv("50.00", Invoice.Status.VOID)

    def test_finance_section_populated_and_excludes_void(self):
        out = get_student_360_summary(self.school.id, self.student.id)
        # The finance section now actually runs (the is_installed("finance") guard
        # matched a bare label that never resolved, so it was silently blank), and
        # only the ISSUED invoice counts — the VOID 50.00 is excluded (was summed
        # before, giving count=2 / total=150.0 that diverged from the finance SOT).
        self.assertIn("invoices_count", out["finance"])
        self.assertEqual(out["finance"]["invoices_count"], 1)
        self.assertEqual(out["finance"]["invoices_total"], 100.0)

    def test_academic_section_now_populated(self):
        # Proves the app-label guard fix: the evals branch runs now (was dead),
        # so the evaluations_count key is present (0 with no evaluations).
        out = get_student_360_summary(self.school.id, self.student.id)
        self.assertIn("evaluations_count", out["academic"])

    def test_all_void_reads_zero(self):
        Invoice.objects.filter(pk=self.live.pk).update(status=Invoice.Status.VOID)
        out = get_student_360_summary(self.school.id, self.student.id)
        self.assertEqual(out["finance"]["invoices_count"], 0)
        self.assertEqual(out["finance"]["invoices_total"], 0.0)
