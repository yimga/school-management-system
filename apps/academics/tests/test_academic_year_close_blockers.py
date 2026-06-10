"""Academic year close — blocker detection."""

from django.test import TestCase

from apps.academics.models import AcademicYear
from apps.academics.year_close import assert_rollover_allowed, evaluate_year_close_blockers
from apps.registries.models import CountryRegistry
from apps.schools.models import School


class AcademicYearCloseBlockersTests(TestCase):
    def setUp(self):
        CountryRegistry.objects.get_or_create(code="CM", defaults={"name": "Cameroon"})
        self.school = School.objects.create(
            name="Block Year",
            slug="block-year",
            subdomain="block-year",
            country_code="CM",
            is_active=True,
        )
        self.other = School.objects.create(
            name="Other",
            slug="other-year",
            subdomain="other-year",
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

    def test_same_year_blocker(self):
        result = evaluate_year_close_blockers(self.school, self.source, self.source)
        self.assertFalse(result["ok"])
        codes = [b["code"] for b in result["blockers"]]
        self.assertIn("same_year", codes)

    def test_tenant_mismatch_blocker(self):
        foreign = AcademicYear.objects.create(
            school=self.other,
            name="Foreign",
            start_date="2024-09-01",
            end_date="2025-06-30",
        )
        result = evaluate_year_close_blockers(self.school, foreign, self.target)
        self.assertFalse(result["ok"])

    def test_assert_rollover_raises(self):
        with self.assertRaises(ValueError):
            assert_rollover_allowed(self.school, self.source, self.source)
