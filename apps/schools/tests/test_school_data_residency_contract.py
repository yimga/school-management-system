"""§0.3 Pillar 1 — data residency fields verifiable on School model."""

from django.test import TestCase

from apps.schools.models import School


class SchoolDataResidencyContractTests(TestCase):
    def test_school_has_residency_related_fields(self):
        s = School.objects.create(
            name="Residency Test",
            slug="residency-test",
            subdomain="residency-test",
            is_active=True,
            compliance_region=School.ComplianceRegion.EU,
        )
        self.assertEqual(s.compliance_region, School.ComplianceRegion.EU)
        self.assertTrue(hasattr(s, "dedicated_db_alias"))
        self.assertTrue(hasattr(s, "default_region_id"))
        s.dedicated_db_alias = "tenant_heavy_1"
        s.save(update_fields=["dedicated_db_alias"])
        s.refresh_from_db()
        self.assertEqual(s.dedicated_db_alias, "tenant_heavy_1")
