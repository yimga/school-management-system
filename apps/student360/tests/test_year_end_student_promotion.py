"""Year-end student promotion contract."""

from django.test import TestCase

from apps.academics.models import AcademicYear
from apps.academics.year_close import evaluate_year_close_blockers
from apps.registries.models import CountryRegistry
from apps.schools.models import School


class YearEndStudentPromotionTests(TestCase):
    def setUp(self):
        CountryRegistry.objects.get_or_create(code="CM", defaults={"name": "Cameroon"})
        self.school = School.objects.create(
            name="Promo School",
            slug="promo-school",
            subdomain="promo-school",
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

    def test_tenant_scoped_blockers(self):
        result = evaluate_year_close_blockers(self.school, self.source, self.target)
        self.assertEqual(result["source_year_id"], str(self.source.pk))
        self.assertEqual(result["target_year_id"], str(self.target.pk))
