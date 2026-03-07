"""
School location / RegionConfig single picker: test that setting default_region on School
persists and is the canonical source for school location.
See docs/SCHOOL_LOCATION_AND_REGION_PICKER.md.
"""
from django.test import TestCase

from apps.schools.models import School


class SchoolRegionPickerTestCase(TestCase):
    """Verify school default_region is set and stored correctly."""

    def test_school_default_region_persists(self):
        """Create a school with default_region; assert default_region_id and optional fields."""
        from apps.siteconfig.models import RegionConfig
        region = RegionConfig.objects.first()
        if not region:
            self.skipTest("No RegionConfig in DB (seed_global_regions or seed_regions).")
        school = School.objects.create(
            name="Test School Region",
            slug="test-school-region",
            subdomain="test-school-region",
            is_active=True,
            default_region=region,
        )
        school.refresh_from_db()
        self.assertEqual(school.default_region_id, region.code)
        self.assertEqual(school.default_region, region)
