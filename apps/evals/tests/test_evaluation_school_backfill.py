"""``Evaluation.school`` must never persist NULL.

Every UI/API write path builds an Evaluation WITHOUT a school: the marks-grid
save (``views._update_evaluations_from_entries``), the OCR apply
(``views._apply_ocr_entries``), the edge offline sync
(``offline_sync.sync_offline_entry``) and both CSV importers
(``importers.apply_import`` / ``apply_import_from_preview``). The column is
nullable, so the row lands with school=NULL and then disappears from every
school-scoped reader:

  * ``views_drilldown.evaluation_drilldown`` filters ``school=request.school``
    whenever request.school is set (always on a tenant host) -> 404 on a mark
    the teacher just entered;
  * the Platform v1 API ``/api/v1/evaluations/`` filters ``school=school`` ->
    lists zero teacher-entered rows;
  * ``views._apply_ocr_entries`` looks the existing row up by
    ``school_id=year.school_id`` -> never matches, so OCR re-creates instead of
    updating;
  * the partial unique index ``uniq_evaluation_school_offline_id`` cannot
    dedupe offline replays, because Postgres treats NULLs as distinct.

Attendance had the identical hole and closed it with a save() chokepoint
(``apps/academics/models.py``); this seals the same chokepoint for Evaluation.
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
    Subject,
    SubjectAssignment,
    Term,
)
from apps.accounts.models import User
from apps.evals.models import Evaluation
from apps.people.models import StudentProfile, TeacherProfile
from apps.schools.models import School


class EvaluationSchoolBackfillTests(TestCase):
    def setUp(self) -> None:
        self.school = School.objects.create(
            name="Backfill High", slug="ev-backfill", subdomain="ev-backfill"
        )
        self.year = AcademicYear.objects.create(
            name="2025/2026-evbf",
            start_date=date(2025, 9, 1),
            end_date=date(2026, 6, 30),
            is_active=True,
        )
        self.term = Term.objects.create(
            academic_year=self.year,
            name=Term.Name.FIRST,
            position=1,
            start_date=date(2025, 9, 1),
            end_date=date(2025, 12, 1),
            is_active=True,
        )
        dept = Department.objects.create(name="Science", code="EVBF-SCI")
        self.specialty = Specialty.objects.create(
            department=dept, name="General", code="EVBF-GEN"
        )
        self.classroom = Classroom.objects.create(
            academic_year=self.year, department=dept, name="EVBF1A", code="EVBF1A"
        )
        subject = Subject.objects.create(name="EVBF Math")
        self.subject_assignment = SubjectAssignment.objects.create(
            academic_year=self.year,
            term=self.term,
            classroom=self.classroom,
            specialty=self.specialty,
            subject=subject,
            coefficient=1.0,
        )
        # School reachable through the STUDENT only -- the shape the marks grid,
        # the OCR apply and the seeders actually produce.
        self.student = StudentProfile.objects.create(
            school=self.school,
            first_name="Ada",
            last_name="Backfill",
            student_code="EVBF01",
            academic_year=self.year,
            classroom=self.classroom,
            specialty=self.specialty,
            is_active=True,
        )
        teacher_user = User.objects.create_user(
            "evbf-teacher", "evbf@ex.com", "pass", role=User.Role.TEACHER
        )
        self.teacher = TeacherProfile.objects.create(user=teacher_user)

    # --- premise guards ---------------------------------------------------

    def test_premise_the_write_paths_really_omit_school(self) -> None:
        """The fixture must reproduce the broken shape, not a pre-scoped one.

        If SubjectAssignment/AcademicYear/Term carried a school the row would be
        school-scoped for the wrong reason and the seal below would be vacuous.
        """
        self.assertIsNone(self.subject_assignment.school_id)
        self.assertIsNone(self.year.school_id)
        self.assertIsNone(self.term.school_id)
        self.assertEqual(self.student.school_id, self.school.pk)

    # --- the seal ---------------------------------------------------------

    def _marks_grid_write(self) -> Evaluation:
        """Exactly what ``_update_evaluations_from_entries`` does: no school."""
        evaluation, _ = Evaluation.objects.update_or_create(
            academic_year=self.year,
            term=self.term,
            subject_assignment=self.subject_assignment,
            student=self.student,
            defaults={"teacher": self.teacher, "seq1_score": Decimal("18.00")},
        )
        return evaluation

    def test_marks_grid_write_backfills_school(self) -> None:
        evaluation = self._marks_grid_write()
        evaluation.refresh_from_db()
        self.assertEqual(evaluation.school_id, self.school.pk)

    def test_school_scoped_readers_see_the_row(self) -> None:
        """The consequence, not just the column: the drilldown / API predicate."""
        self._marks_grid_write()
        # Guard against a vacuous pass: the row has to exist unscoped first.
        self.assertEqual(Evaluation.objects.count(), 1)
        self.assertEqual(
            Evaluation.objects.filter(school=self.school).count(),
            1,
            "views_drilldown/api_views filter school=request.school; a NULL "
            "school makes the teacher's own mark 404 / vanish from the API",
        )

    def test_explicit_school_is_not_overwritten(self) -> None:
        other = School.objects.create(
            name="Other Backfill", slug="ev-backfill-2", subdomain="ev-backfill-2"
        )
        evaluation = Evaluation.objects.create(
            school=other,
            academic_year=self.year,
            term=self.term,
            subject_assignment=self.subject_assignment,
            student=self.student,
            teacher=self.teacher,
            seq1_score=Decimal("11.00"),
        )
        evaluation.refresh_from_db()
        # Backfill fires only on NULL -- an explicit school stands.
        self.assertEqual(evaluation.school_id, other.pk)

    def test_update_branch_heals_a_legacy_null_row(self) -> None:
        evaluation = self._marks_grid_write()
        # Simulate a row written before the chokepoint, bypassing save().
        Evaluation.objects.filter(pk=evaluation.pk).update(school=None)
        self.assertIsNone(Evaluation.objects.get(pk=evaluation.pk).school_id)

        stale = Evaluation.objects.get(pk=evaluation.pk)
        stale.seq1_score = Decimal("19.00")
        # update_fields is the shape update_or_create's UPDATE branch uses; the
        # backfill has to widen it or the healed value is never written.
        stale.save(update_fields=["seq1_score"])

        healed = Evaluation.objects.get(pk=evaluation.pk)
        self.assertEqual(healed.school_id, self.school.pk)
        self.assertEqual(healed.seq1_score, Decimal("19.00"))


class EvaluationSchoolDataMigrationTests(EvaluationSchoolBackfillTests):
    """Migration 0040 must heal the rows written before the chokepoint landed."""

    def test_migration_backfills_a_legacy_null_row_from_the_student(self) -> None:
        from importlib import import_module

        from django.apps import apps as django_apps

        # The module name starts with a digit, so it cannot be imported with a
        # plain `from ... import`.
        _backfill = import_module(
            "apps.evals.migrations.0040_backfill_evaluation_school"
        )._backfill

        evaluation = self._marks_grid_write()
        Evaluation.objects.filter(pk=evaluation.pk).update(school=None)
        self.assertIsNone(Evaluation.objects.get(pk=evaluation.pk).school_id)

        _backfill(django_apps, None)

        self.assertEqual(
            Evaluation.objects.get(pk=evaluation.pk).school_id, self.school.pk
        )
