"""Academic year close — dry run orchestrator."""

from django.test import TestCase

from apps.academics.models import AcademicYear
from apps.academics.year_close import execute_year_close, run_year_close_dry_run
from apps.registries.models import CountryRegistry
from apps.schools.models import School


class AcademicYearCloseDryRunTests(TestCase):
    def setUp(self):
        CountryRegistry.objects.get_or_create(code="CM", defaults={"name": "Cameroon"})
        self.school = School.objects.create(
            name="Year School",
            slug="year-school",
            subdomain="year-school",
            country_code="CM",
            is_active=True,
        )
        self.source = AcademicYear.objects.create(
            school=self.school,
            name="2024-25",
            start_date="2024-09-01",
            end_date="2025-06-30",
        )
        self.target = AcademicYear.objects.create(
            school=self.school,
            name="2025-26",
            start_date="2025-09-01",
            end_date="2026-06-30",
        )

    def test_run_year_close_dry_run_returns_scorecard(self):
        result = run_year_close_dry_run(self.school, self.source, self.target)
        self.assertTrue(result["dry_run"])
        self.assertIn("blockers", result)

    def test_execute_year_close_default_dry_run_no_writes(self):
        result = execute_year_close(self.school, self.source, self.target, dry_run=True)
        self.assertTrue(result["dry_run"])
        self.source.refresh_from_db()
        self.assertFalse(self.source.is_locked)
