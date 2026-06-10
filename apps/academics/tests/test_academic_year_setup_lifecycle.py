"""Academic year lifecycle tests."""

from datetime import date

from django.test import TestCase

from apps.academics.models import AcademicYear, Term
from apps.academics.year_close import assert_rollover_allowed, evaluate_year_close_blockers
from apps.schools.models import School


class AcademicYearLifecycleTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Year School",
            slug="year-school",
            subdomain="year-school",
            is_active=True,
        )
        self.source = AcademicYear.objects.create(
            school=self.school,
            name="2024-25",
            start_date=date(2024, 9, 1),
            end_date=date(2025, 6, 30),
        )
        self.target = AcademicYear.objects.create(
            school=self.school,
            name="2025-26",
            start_date=date(2025, 9, 1),
            end_date=date(2026, 6, 30),
        )
        Term.objects.create(
            school=self.school,
            academic_year=self.source,
            name="Term 1",
            start_date=date(2024, 9, 1),
            end_date=date(2024, 12, 15),
        )

    def test_dry_run_flags_unpublished_terms(self):
        result = evaluate_year_close_blockers(self.school, self.source, self.target)
        self.assertTrue(result["dry_run"])
        codes = {b["code"] for b in result["blockers"]}
        self.assertIn("terms_unpublished", codes)

    def test_same_year_blocked(self):
        result = evaluate_year_close_blockers(self.school, self.source, self.source)
        self.assertFalse(result["ok"])

    def test_assert_rollover_raises_on_blockers(self):
        with self.assertRaises(ValueError):
            assert_rollover_allowed(self.school, self.source, self.target)

    def test_tenant_scope_mismatch(self):
        other = School.objects.create(
            name="Other",
            slug="other-school",
            subdomain="other-school",
            is_active=True,
        )
        foreign = AcademicYear.objects.create(
            school=other,
            name="Foreign",
            start_date=date(2024, 9, 1),
            end_date=date(2025, 6, 30),
        )
        result = evaluate_year_close_blockers(self.school, foreign, self.target)
        self.assertFalse(result["ok"])
