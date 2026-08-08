"""Playbook bulk student + grade import — REAL appliers (2026-08-08).

``automation.playbook_executor._run_one_step`` imports
``accounts.migration_services.run_student_import`` / ``run_grade_import`` inside a
``try/except ImportError``. For a long time neither existed, so every real
playbook student/grade step silently reported ``*_service_unavailable`` — honest
degradation, but the feature never actually worked.

They are now real, routing through the SAME apply paths the interactive surfaces
use (the bulk-CSV onboarding kernel for students, the grade-import job service
for grades). These DB-backed tests are the seal:

* students   — create, dedupe idempotently on re-run, stay tenant-scoped, and a
  bad row rejects the batch with named errors (no partial silent writes);
* grades     — create, update-in-place on re-run, land under the SCHOOL'S OWN
  academic year (never another tenant's), and record an auditable job.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from django.test import TestCase

from apps.accounts.migration_services import run_grade_import, run_student_import


class RunStudentImportTests(TestCase):
    """The bulk-CSV kernel, driven by playbook row-dicts."""

    def _school(self, slug):
        from apps.schools.models import School

        return School.objects.create(
            name=slug, slug=slug, subdomain=slug, country_code="CM"
        )

    def _rows(self):
        return [
            {"student_code": "SIS-1", "first_name": "Ada", "last_name": "Lovelace"},
            {
                "student_code": "SIS-2",
                "first_name": "Alan",
                "last_name": "Turing",
                "email": "alan@example.com",
            },
        ]

    def test_creates_students_with_tenant_scoped_codes(self):
        from apps.people.models import StudentProfile

        school = self._school("stud-a")
        result = run_student_import(school, self._rows())

        self.assertEqual(result["created"], 2, result)
        self.assertEqual(result["errors"], [])
        self.assertEqual(
            StudentProfile.objects.filter(school=school).count(), 2
        )
        codes = set(
            StudentProfile.objects.filter(school=school).values_list(
                "student_code", flat=True
            )
        )
        self.assertEqual(
            codes, {f"S{school.pk}-SIS-1", f"S{school.pk}-SIS-2"}
        )

    def test_reruns_are_idempotent(self):
        from apps.people.models import StudentProfile

        school = self._school("stud-b")
        run_student_import(school, self._rows())
        again = run_student_import(school, self._rows())

        self.assertEqual(again["created"], 0, again)
        self.assertEqual(again["skipped"], 2, again)
        self.assertEqual(
            StudentProfile.objects.filter(school=school).count(),
            2,
            "a re-run must not duplicate students",
        )

    def test_import_is_tenant_scoped(self):
        from apps.people.models import StudentProfile

        a = self._school("stud-t-a")
        b = self._school("stud-t-b")

        run_student_import(a, self._rows())
        # The SAME source identifiers imported into a second school must create
        # fresh students there and never collide with — or touch — school A.
        result_b = run_student_import(b, self._rows())
        self.assertEqual(result_b["created"], 2, result_b)

        a_codes = set(
            StudentProfile.objects.filter(school=a).values_list(
                "student_code", flat=True
            )
        )
        b_codes = set(
            StudentProfile.objects.filter(school=b).values_list(
                "student_code", flat=True
            )
        )
        self.assertEqual(a_codes, {f"S{a.pk}-SIS-1", f"S{a.pk}-SIS-2"})
        self.assertEqual(b_codes, {f"S{b.pk}-SIS-1", f"S{b.pk}-SIS-2"})
        self.assertEqual(
            a_codes & b_codes, set(), "tenant code namespaces must be disjoint"
        )

    def test_a_bad_row_rejects_the_batch_with_named_errors(self):
        from apps.people.models import StudentProfile

        school = self._school("stud-c")
        rows = [
            {"student_code": "OK-1", "first_name": "Grace", "last_name": "Hopper"},
            # last_name missing -> the whole batch is rejected (all-or-nothing),
            # so no half-written import lands.
            {"student_code": "BAD-2", "first_name": "Nolast", "last_name": ""},
        ]
        result = run_student_import(school, rows)

        self.assertEqual(result["created"], 0, result)
        self.assertTrue(result["errors"], "the failing row must be named")
        self.assertEqual(
            StudentProfile.objects.filter(school=school).count(),
            0,
            "a rejected batch must write nothing",
        )


class RunGradeImportTests(TestCase):
    """The grade-import job service, driven by playbook row-dicts."""

    def setUp(self):
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
        from apps.evals.models import TeacherAssignment
        from apps.people.models import StudentProfile, TeacherProfile
        from apps.schools.models import School

        self.school = School.objects.create(
            name="Grade S1", slug="grade-s1", subdomain="grade-s1", country_code="CM"
        )
        self.year = AcademicYear.objects.create(
            name="2025/2026",
            start_date=date(2025, 9, 1),
            end_date=date(2026, 6, 30),
            is_active=True,
            school=self.school,
        )
        self.term = Term.objects.create(
            name=Term.Name.FIRST,
            academic_year=self.year,
            position=1,
            start_date=date(2025, 9, 1),
            end_date=date(2025, 12, 1),
            school=self.school,
        )
        self.dept = Department.objects.create(
            name="Science", code="SCI-G", school=self.school
        )
        self.spec = Specialty.objects.create(
            name="General", code="GEN-G", department=self.dept, school=self.school
        )
        self.classroom = Classroom.objects.create(
            name="Form 1",
            code="F1-G",
            academic_year=self.year,
            department=self.dept,
            school=self.school,
        )
        self.subject = Subject.objects.create(name="Math G", school=self.school)
        self.assignment = SubjectAssignment.objects.create(
            academic_year=self.year,
            term=self.term,
            classroom=self.classroom,
            specialty=self.spec,
            subject=self.subject,
            coefficient=1,
            school=self.school,
        )
        self.student = StudentProfile.objects.create(
            school=self.school,
            first_name="Jo",
            last_name="Row",
            student_code="G-1",
            academic_year=self.year,
            classroom=self.classroom,
            specialty=self.spec,
        )
        self.teacher = TeacherProfile.objects.create(
            user=User.objects.create_user(username="grade_teacher", password="p"),
            school=self.school,
        )
        TeacherAssignment.objects.create(
            teacher=self.teacher,
            academic_year=self.year,
            subject_assignment=self.assignment,
            school=self.school,
            is_active=True,
        )

    def _row(self, **overrides):
        row = {
            "student_code": "G-1",
            "subject_assignment_id": str(self.assignment.id),
            "term_id": str(self.term.id),
            "teacher_username": "grade_teacher",
            "seq1": "12",
            "seq2": "13",
            "exam": "14",
            "mock": "",
            "practical": "",
            "remarks": "",
        }
        row.update(overrides)
        return row

    def test_creates_evaluation_and_audit_job(self):
        from apps.analytics.models import GradeImportJob
        from apps.evals.models import Evaluation

        result = run_grade_import(self.school, [self._row()], user=None)

        self.assertEqual(result["created"], 1, result)
        ev = Evaluation.objects.get(
            student=self.student,
            subject_assignment=self.assignment,
            term=self.term,
        )
        self.assertEqual(
            ev.academic_year_id,
            self.year.id,
            "the grade must land under the school's own year",
        )
        self.assertEqual(ev.seq1_score, Decimal("12"))
        self.assertEqual(ev.teacher_id, self.teacher.id)

        job = GradeImportJob.objects.filter(
            academic_year=self.year, term=self.term
        ).latest("created_at")
        self.assertEqual(job.status, "completed")
        self.assertEqual(job.created_count, 1)
        self.assertEqual(job.total_rows, 1)

    def test_rerun_updates_in_place_not_duplicate(self):
        from apps.evals.models import Evaluation

        run_grade_import(self.school, [self._row()])
        again = run_grade_import(self.school, [self._row(seq1="18")])

        self.assertEqual(again["created"], 0, again)
        self.assertEqual(again["updated"], 1, again)
        self.assertEqual(
            Evaluation.objects.filter(student=self.student).count(),
            1,
            "the same (year, term, assignment, student) key must update, not add",
        )
        ev = Evaluation.objects.get(student=self.student)
        self.assertEqual(ev.seq1_score, Decimal("18"))

    def test_year_resolution_is_tenant_scoped(self):
        from apps.academics.models import AcademicYear
        from apps.evals.models import Evaluation
        from apps.schools.models import School

        # A second school with its own active year must be untouched, and its
        # year must never be the one the import writes under.
        other = School.objects.create(
            name="Grade S2", slug="grade-s2", subdomain="grade-s2", country_code="CM"
        )
        AcademicYear.objects.create(
            name="2025/2026-b",
            start_date=date(2025, 9, 1),
            end_date=date(2026, 6, 30),
            is_active=True,
            school=other,
        )

        run_grade_import(self.school, [self._row()])

        self.assertTrue(
            Evaluation.objects.filter(academic_year__school=self.school).exists()
        )
        self.assertFalse(
            Evaluation.objects.filter(academic_year__school=other).exists(),
            "a playbook grade import must not write another tenant's year",
        )
