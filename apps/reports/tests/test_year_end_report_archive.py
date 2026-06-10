"""Year-end report archive contract."""

from django.test import TestCase

from apps.academics.models import AcademicYear
from apps.academics.year_close import run_year_close_dry_run
from apps.registries.models import CountryRegistry
from apps.schools.models import School


class YearEndReportArchiveTests(TestCase):
    def setUp(self):
        CountryRegistry.objects.get_or_create(code="CM", defaults={"name": "Cameroon"})
        self.school = School.objects.create(
            name="Report School",
            slug="report-school",
            subdomain="report-school",
            country_code="CM",
            is_active=True,
        )
        self.source = AcademicYear.objects.create(
            school=self.school,
            name="2024-2025",
            start_date="2024-09-01",
            end_date="2025-06-30",
        )
        self.target = AcademicYear.objects.create(
            school=self.school,
            name="2025-2026",
            start_date="2025-09-01",
            end_date="2026-06-30",
        )

    def test_dry_run_includes_scorecard(self):
        result = run_year_close_dry_run(self.school, self.source, self.target)
        self.assertIn("blockers", result)
        self.assertTrue(result["dry_run"])
