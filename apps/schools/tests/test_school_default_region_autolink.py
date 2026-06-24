"""School.default_region auto-link on save (read-only region lookup)."""

from __future__ import annotations

import uuid

from django.test import TestCase

from apps.schools.models import School
from apps.siteconfig.models_platform_catalog import RegionConfig


class SchoolDefaultRegionAutolinkTests(TestCase):
    @staticmethod
    def _school(**kw):
        tag = uuid.uuid4().hex[:10]
        defaults = {
            "name": f"Autolink {tag}",
            "slug": f"autolink-{tag}",
            "subdomain": f"autolink-{tag}",
            "is_active": False,
        }
        defaults.update(kw)
        return School.objects.create(**defaults)

    @staticmethod
    def _region(code: str, name: str) -> RegionConfig:
        region, _ = RegionConfig.objects.get_or_create(
            code=code, defaults={"name": name}
        )
        return region

    def test_save_links_alpha2_country_to_existing_region(self):
        self._region("CMR", "Cameroon")
        school = self._school(country_code="CM", default_region=None)
        self.assertEqual(school.default_region_id, "CMR")

    def test_save_links_alpha3_country_code_when_region_exists(self):
        self._region("USA", "United States")
        school = self._school(country_code="US", default_region=None)
        self.assertEqual(school.default_region_id, "USA")

    def test_save_does_not_override_explicit_default_region(self):
        usa = self._region("USA", "United States")
        cmr = self._region("CMR", "Cameroon")
        school = self._school(
            country_code="US",
            default_region=cmr,
        )
        self.assertEqual(school.default_region_id, cmr.code)
        self.assertNotEqual(school.default_region_id, usa.code)

    def test_save_leaves_region_null_when_no_matching_row(self):
        school = self._school(country_code="ZZ", default_region=None)
        self.assertIsNone(school.default_region_id)

    def test_save_respects_update_fields_without_default_region(self):
        self._region("CMR", "Cameroon")
        school = self._school(country_code="CM", default_region=None)
        self.assertEqual(school.default_region_id, "CMR")

        school.name = "Renamed only"
        school.save(update_fields=["name"])
        school.refresh_from_db()
        self.assertEqual(school.default_region_id, "CMR")

    def test_save_links_when_update_fields_includes_default_region(self):
        self._region("CMR", "Cameroon")
        school = self._school(country_code="", default_region=None)
        self.assertIsNone(school.default_region_id)
        school.country_code = "CM"
        school.save(update_fields=["country_code", "default_region"])
        self.assertEqual(school.default_region_id, "CMR")
