"""Academic year rollover — tenant scope."""

from django.test import TestCase

from apps.academics.models import AcademicYear
from apps.academics.year_close import lock_source_year
from apps.registries.models import CountryRegistry
from apps.schools.models import School


class AcademicYearRolloverTenantScopeTests(TestCase):
    def setUp(self):
        CountryRegistry.objects.get_or_create(code="CM", defaults={"name": "Cameroon"})
        self.school = School.objects.create(
            name="Scope School",
            slug="scope-school",
            subdomain="scope-school",
            country_code="CM",
            is_active=True,
        )
        self.other = School.objects.create(
            name="Other Scope",
            slug="other-scope",
            subdomain="other-scope",
            country_code="CM",
            is_active=True,
        )
        self.year = AcademicYear.objects.create(
            school=self.school,
            name="2024-25",
            start_date="2024-09-01",
            end_date="2025-06-30",
        )

    def test_lock_source_year_tenant_scoped(self):
        result = lock_source_year(self.school, self.year)
        self.assertTrue(result["ok"])
        self.year.refresh_from_db()
        self.assertTrue(self.year.is_locked)

    def test_lock_rejects_wrong_school(self):
        foreign = AcademicYear.objects.create(
            school=self.other,
            name="Foreign",
            start_date="2024-09-01",
            end_date="2025-06-30",
        )
        with self.assertRaises(ValueError):
            lock_source_year(self.school, foreign)
