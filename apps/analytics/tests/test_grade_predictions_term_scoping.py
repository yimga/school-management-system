"""compute_nightly_grade_predictions must resolve ONE tenant's open term.

The term lookup carried no ``school=`` predicate, so on the single-schema
(RLS) deployment every school in the loop was handed the globally-newest open
Term. Every school but the one that owns that term then matched zero students
and silently wrote nothing, while the command still reported success.
"""

from __future__ import annotations

import uuid
from io import StringIO

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from apps.academics.models import (
    AcademicYear,
    Classroom,
    Department,
    Specialty,
    Subject,
    SubjectAssignment,
    Term,
)
from apps.analytics.models import GradePrediction
from apps.people.models import StudentProfile
from apps.schools.models import School


class _Tenant:
    """One fully-wired school: year, term, classroom, assignment, student."""

    def __init__(self, label: str, *, term_start_offset_days: int):
        uid = uuid.uuid4().hex[:8]
        today = timezone.now().date()
        self.school = School.objects.create(
            name=f"{label} {uid}",
            slug=f"{label.lower()}-{uid}",
            subdomain=f"{label.lower()}-{uid}",
            is_active=True,
        )
        self.year = AcademicYear.objects.create(
            school=self.school,
            name=f"{label}Y-{uid}",
            start_date=today - timezone.timedelta(days=200),
            end_date=today + timezone.timedelta(days=165),
        )
        self.term = Term.objects.create(
            school=self.school,
            academic_year=self.year,
            name=f"{label}T-{uid}"[:20],
            start_date=today - timezone.timedelta(days=term_start_offset_days),
            end_date=today + timezone.timedelta(days=60),
        )
        self.department = Department.objects.create(
            school=self.school, name=f"{label} Dept", code=f"D{uid[:6]}"
        )
        self.specialty = Specialty.objects.create(
            school=self.school,
            department=self.department,
            name=f"{label} Spec",
            code=f"S{uid[:6]}",
        )
        self.classroom = Classroom.objects.create(
            school=self.school,
            academic_year=self.year,
            department=self.department,
            name=f"{label} Class",
            code=f"C{uid[:6]}",
        )
        self.subject = Subject.objects.create(
            school=self.school, name=f"{label} Maths"
        )
        self.assignment = SubjectAssignment.objects.create(
            school=self.school,
            academic_year=self.year,
            term=self.term,
            classroom=self.classroom,
            specialty=self.specialty,
            subject=self.subject,
        )
        self.student = StudentProfile.objects.create(
            school=self.school,
            classroom=self.classroom,
            first_name=label,
            last_name="Student",
            student_code=f"sc-{uid}",
            admission_number=f"ad-{uid}",
            is_active=True,
        )


class GradePredictionTermScopingTests(TestCase):
    def setUp(self):
        # "other" opens its term one day later, so it wins a global
        # ``order_by("-start_date")`` over the school we actually ask for.
        self.mine = _Tenant("Mine", term_start_offset_days=10)
        self.other = _Tenant("Other", term_start_offset_days=1)

    def _run(self, tenant):
        out = StringIO()
        call_command(
            "compute_nightly_grade_predictions",
            "--school", str(tenant.school.id),
            stdout=out,
            stderr=out,
        )
        return out.getvalue()

    def test_predictions_are_written_against_the_schools_own_open_term(self):
        # Guard against the vacuous pass: the fixture must actually give this
        # school something to predict, otherwise "0 rows" would be correct.
        self.assertTrue(
            SubjectAssignment.objects.filter(term=self.mine.term).exists()
        )
        self.assertTrue(
            StudentProfile.objects.filter(
                school=self.mine.school, classroom=self.mine.classroom, is_active=True
            ).exists()
        )

        self._run(self.mine)

        rows = list(GradePrediction.objects.filter(school=self.mine.school))
        self.assertEqual(
            len(rows), 1,
            "no prediction was written for a school with an open term, an "
            "assignment and an enrolled student",
        )
        self.assertEqual(rows[0].term_id, self.mine.term.pk)

    def test_no_prediction_borrows_the_other_tenants_term(self):
        self._run(self.mine)
        self.assertFalse(
            GradePrediction.objects.filter(term=self.other.term).exists(),
            "predictions were attributed to another tenant's term",
        )
        self.assertFalse(
            GradePrediction.objects.filter(school=self.other.school).exists()
        )
