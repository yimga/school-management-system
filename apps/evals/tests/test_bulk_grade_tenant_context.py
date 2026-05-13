from datetime import date
from unittest.mock import patch

from django.test import TestCase, tag

from apps.academics.models import AcademicYear, Term
from apps.evals.tasks import _infer_school_id_for_bulk_grades
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
