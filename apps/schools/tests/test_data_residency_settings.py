"""GEOS-99 batch 1388: School.settings data_residency JSON bridge."""

from django.test import TestCase

from apps.schools.data_residency_settings import (
    get_data_residency_payload,
    residency_middleware_guard,
    set_data_residency_payload,
)
from apps.schools.models import School


class DataResidencySettingsTests(TestCase):
    def test_settings_json_roundtrip(self):
        school = School.objects.create(
            name="Res School",
            slug="res-school",
            subdomain="res-school",
            is_active=True,
            country_code="FR",
        )
        set_data_residency_payload(
            school,
            {"region_code": "eu_central", "enforcement": "strict", "corridor_id": "eu-fr"},
        )
        school.save()
        school.refresh_from_db()
        payload = get_data_residency_payload(school)
        self.assertEqual(payload["region_code"], "eu_central")
        self.assertEqual(payload["enforcement"], "strict")
        self.assertEqual(payload["corridor_id"], "eu-fr")
        self.assertTrue(residency_middleware_guard(school, "eu_central"))
        self.assertFalse(residency_middleware_guard(school, "us_east"))
