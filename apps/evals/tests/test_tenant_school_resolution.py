"""A NULL ``school`` FK must not silently widen the grading scale.

``resolve_school_score_scale(None)`` returns a neutral 100, so every link in the
resolution chain that comes back empty makes validation MORE permissive. Under
schema-per-tenant the per-row ``school`` FK is redundant (the schema isolates the
tenant), so seeders and bulk writers routinely omit it — on a real Buea/Cameroon
tenant that meant an Evaluation of **25 on a /20 scale was accepted**, silently
corrupting every average computed from it.

These are must-FIRE tests: each asserts the guard actually rejects, and one
asserts a valid in-scale mark is still accepted so the fix cannot over-tighten.
SQLite cannot create tenant schemas, so the connection leg is exercised by
patching the resolver — the chain order is what is under test here, and the live
schema behaviour is covered against real Postgres.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from unittest import mock

from django.core.exceptions import ValidationError
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


class EvaluationTenantSchoolResolutionTests(TestCase):
    """The score bound must survive a NULL school on the row and its assignment."""

    @classmethod
    def setUpTestData(cls):
        cls.school = School.objects.create(
            name="Buea Scale School",
            slug="buea-scale-school",
            subdomain="buea-scale-school",
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
        cls.term = Term.objects.create(
            school=cls.school,
            academic_year=cls.year,
            name=Term.Name.FIRST,
            position=1,
            start_date=date(2025, 9, 1),
            end_date=date(2025, 12, 15),
            is_active=True,
        )
        dept = Department.objects.create(
            school=cls.school, name="General", code="GEN-SCALE"
        )
        cls.specialty = Specialty.objects.create(
            school=cls.school, department=dept, name="General", code="GENSPEC-SCALE"
        )
        cls.classroom = Classroom.objects.create(
            school=cls.school,
            academic_year=cls.year,
            department=dept,
            name="Form 1",
            code="F1-SCALE",
        )
        subject = Subject.objects.create(school=cls.school, name="Mathematics")
        # school deliberately left NULL here — this is the seeded shape.
        cls.assignment = SubjectAssignment.objects.create(
            academic_year=cls.year,
            term=cls.term,
            classroom=cls.classroom,
            specialty=cls.specialty,
            subject=subject,
            coefficient=1,
        )
        teacher_user = User.objects.create_user(
            username="scale_teacher", password="x", role=User.Role.TEACHER
        )
        cls.teacher = TeacherProfile.objects.create(
            user=teacher_user, school=cls.school
        )
        # Cameroon: marks are out of 20.
        AssessmentWeights.objects.create(
            school=cls.school, academic_year=cls.year, score_scale=20
        )

    def _student(self, code, *, school):
        return StudentProfile.objects.create(
            school=school,
            first_name="Ndi",
            last_name=code,
            student_code=code,
            academic_year=self.year,
            classroom=self.classroom,
            specialty=self.specialty,
            is_active=True,
        )

    def _evaluation(self, student, score):
        return Evaluation(
            academic_year=self.year,
            term=self.term,
            subject_assignment=self.assignment,
            student=student,
            teacher=self.teacher,
            seq1_score=Decimal(score),
        )

    def test_out_of_scale_rejected_via_student_when_row_and_assignment_null(self):
        """Row school NULL + assignment school NULL -> student still bounds it."""
        student = self._student("SCALE-1", school=self.school)
        with self.assertRaises(ValidationError):
            self._evaluation(student, "25.00").save()

    def test_out_of_scale_rejected_via_connection_when_whole_graph_null(self):
        """Every FK NULL -> the connection's tenant is the last line of defence.

        This is the exact seeded shape that let 25/20 through on real Postgres.
        """
        student = self._student("SCALE-2", school=None)
        with mock.patch(
            "apps.schools.rls_context.resolve_connection_school",
            return_value=self.school,
        ):
            with self.assertRaises(ValidationError):
                self._evaluation(student, "25.00").save()

    def test_in_scale_mark_still_accepted(self):
        """The fix must not over-tighten: a valid /20 mark still saves."""
        student = self._student("SCALE-3", school=self.school)
        evaluation = self._evaluation(student, "18.00")
        evaluation.save()
        self.assertIsNotNone(evaluation.pk)

    def test_resolver_is_consulted_only_as_last_resort(self):
        """A school on the row short-circuits the chain — no connection lookup."""
        student = self._student("SCALE-4", school=self.school)
        evaluation = self._evaluation(student, "18.00")
        evaluation.school = self.school
        with mock.patch(
            "apps.schools.rls_context.resolve_connection_school"
        ) as resolver:
            evaluation.save()
        resolver.assert_not_called()
