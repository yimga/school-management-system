from datetime import date
from unittest.mock import patch

from django.test import TestCase, tag

from apps.academics.models import AcademicYear, Term
from apps.evals.tasks import _infer_school_id_for_bulk_grades, process_bulk_grades
from apps.people.models import StudentProfile
from apps.schools.models import School
from apps.schools.rls_context import rls_bypass


@tag("tenants_rls")
class BulkGradeTenantContextTests(TestCase):
    def test_infers_school_id_from_academic_year_and_term_for_rls(self):
        with rls_bypass():
            school = School.objects.create(
                name="Bulk Grade School",
                slug="bulk-grade-school",
                subdomain="bulk-grade-school",
                is_active=True,
            )
            year = AcademicYear.objects.create(
                school=school,
                name="2025/2026",
                start_date=date(2025, 9, 1),
                end_date=date(2026, 7, 1),
            )
            term = Term.objects.create(
                school=school,
                academic_year=year,
                name="Term 1",
                start_date=date(2025, 9, 1),
                end_date=date(2025, 12, 1),
            )

        with patch("apps.evals.tasks._requires_explicit_rls_context", return_value=True):
            self.assertEqual(
                _infer_school_id_for_bulk_grades(
                    academic_year_id=year.pk,
                    term_id=term.pk,
                ),
                str(school.pk),
            )

    def test_inference_rejects_identifiers_spanning_multiple_schools(self):
        with rls_bypass():
            school_a = School.objects.create(
                name="Bulk Grade School A",
                slug="bulk-grade-school-a",
                subdomain="bulk-grade-school-a",
                is_active=True,
            )
            school_b = School.objects.create(
                name="Bulk Grade School B",
                slug="bulk-grade-school-b",
                subdomain="bulk-grade-school-b",
                is_active=True,
            )
            student_a = StudentProfile.objects.create(
                school=school_a,
                first_name="Ada",
                last_name="A",
                student_code="BULK-A",
            )
            student_b = StudentProfile.objects.create(
                school=school_b,
                first_name="Ben",
                last_name="B",
                student_code="BULK-B",
            )

        with patch("apps.evals.tasks._requires_explicit_rls_context", return_value=True):
            with self.assertRaisesMessage(
                ValueError, "identifiers span multiple schools"
            ):
                _infer_school_id_for_bulk_grades(
                    student_ids=[student_a.pk, student_b.pk],
                )

    def test_process_bulk_grades_refuses_unscoped_rls_run(self):
        with patch("apps.evals.tasks._requires_explicit_rls_context", return_value=True):
            with self.assertRaisesMessage(ValueError, "requires schema_name or school_id"):
                process_bulk_grades.run(
                    student_ids=[],
                    academic_year_id=None,
                    term_id=None,
                    schema_name=None,
                    school_id=None,
                )
