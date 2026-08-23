"""``Evaluation.normalized_value`` must use the RESOLVED grading school.

``Evaluation.school`` is nullable and, per ``_resolve_grading_school``'s own
docstring, "frequently unset -- schema isolation makes it redundant, so seeders
and bulk writers omit it". The score-BOUNDS path in the same ``save()`` already
resolves the school by walking the object graph; the normalized_value block read
the raw FK instead and so passed None for ordinary rows.

For a /100 school that is real corruption. ``score_to_normalized`` falls back to
the legacy /20 basis when given no school, and clamps the result to [0, 1] -- so
every mark >= 20 collapses to 1.0000 and 20/100 becomes indistinguishable from
100/100, both in the cross-system Rosetta Stone value and in the report-card
remark band derived from it.

The /20 default INSIDE score_to_normalized is deliberate and untouched here: it
is pinned for genuinely schoolless calls by
reports/tests/test_auto_teacher_remark.py::test_legacy_20_preserved_via_default_scale
(historical francophone behaviour). The bug was the caller, not the default.
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase

from apps.academics.models import (
    AcademicYear,
    Classroom,
    Department,
    Specialty,
    Subject,
    SubjectAssignment,
    Term,
)
from apps.accounts.models import User
from apps.evals.models import AssessmentWeights, Evaluation
from apps.people.models import StudentProfile, TeacherProfile
from apps.schools.models import School


class NormalizedValueUsesResolvedSchoolTests(TestCase):
    def setUp(self) -> None:
        self.school = School.objects.create(
            name="Percent High", slug="nv-percent", subdomain="nv-percent"
        )
        self.year = AcademicYear.objects.create(
            name="2025/2026",
            start_date="2025-09-01",
            end_date="2026-08-31",
            is_active=True,
        )
        self.term = Term.objects.create(
            academic_year=self.year,
            name=Term.Name.FIRST,
            position=1,
            start_date="2025-09-01",
            end_date="2025-11-30",
            is_active=True,
        )
        dept = Department.objects.create(name="Science", code="NV-SCI")
        specialty = Specialty.objects.create(
            department=dept, name="General", code="NV-GEN"
        )
        classroom = Classroom.objects.create(
            academic_year=self.year, department=dept, name="NV1A", code="NV1A"
        )
        subject = Subject.objects.create(name="NV Math")
        self.subject_assignment = SubjectAssignment.objects.create(
            academic_year=self.year,
            term=self.term,
            classroom=classroom,
            specialty=specialty,
            subject=subject,
            coefficient=1.0,
        )
        # The school is reachable through the STUDENT, not through the
        # Evaluation's own FK -- exactly the shape _resolve_grading_school exists
        # for, and the shape seeders and bulk writers produce.
        self.student = StudentProfile.objects.create(
            school=self.school,
            first_name="A",
            last_name="Student",
            student_code="NV01",
            academic_year=self.year,
            classroom=classroom,
            specialty=specialty,
            is_active=True,
        )
        teacher_user = User.objects.create_user(
            "nv-teacher", "nv@ex.com", "pass", role=User.Role.TEACHER
        )
        self.teacher = TeacherProfile.objects.create(user=teacher_user)
        AssessmentWeights.objects.create(
            academic_year=self.year,
            term=self.term,
            classroom=classroom,
            seq1_weight=0,
            seq2_weight=0,
            exam_weight=100,
            mock_weight=0,
            practical_weight=0,
            score_scale=100,
        )

    def _save_evaluation(self):
        # A /100 school: the tenant grading schema is what get_scale_for_school
        # reads, so drive it directly rather than seeding siteconfig.
        with patch(
            "apps.siteconfig.tenant_config.get_grading_schema_for_school",
            return_value={"scale": "0-100"},
        ):
            return Evaluation.objects.create(
                school=None,  # the common case
                academic_year=self.year,
                term=self.term,
                subject_assignment=self.subject_assignment,
                student=self.student,
                teacher=self.teacher,
                exam_score=Decimal("80.0"),
            )

    def test_percentage_school_80_normalizes_to_0_80_not_1_0(self) -> None:
        ev = self._save_evaluation()
        self.assertEqual(ev.final_score, Decimal("80.00"))
        self.assertIsNotNone(ev.normalized_value)
        # Reading the raw (None) FK gives the /20 basis -> 80/20 clamps to 1.0000.
        self.assertNotEqual(
            ev.normalized_value.quantize(Decimal("0.0001")),
            Decimal("1.0000"),
            "80 on a /100 school must not saturate the normalized value",
        )
        self.assertAlmostEqual(float(ev.normalized_value), 0.80, places=2)

    def test_evaluation_school_fk_is_backfilled_from_the_same_resolver(self) -> None:
        # Was ``test_evaluation_school_fk_is_still_none``: this fix had to
        # resolve the school WITHOUT backfilling the FK, because backfilling
        # was "a separate concern". That separate concern has since landed --
        # Evaluation.save() now derives the tenant FK from this very same
        # walker (see tests/test_evaluation_school_backfill.py), so the row no
        # longer persists NULL. What still matters here is that the value comes
        # from the RESOLVER and not from what the writer passed in: the caller
        # above passes school=None explicitly.
        ev = self._save_evaluation()
        ev.refresh_from_db()
        self.assertEqual(ev.school_id, self.school.pk)
