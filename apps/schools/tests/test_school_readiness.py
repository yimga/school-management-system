from django.test import TestCase

from apps.registries.models import CountryRegistry
from apps.siteconfig.models_platform_catalog import RegionConfig
from apps.schools.models import School
from apps.schools.school_readiness import build_school_readiness


class SchoolReadinessTests(TestCase):
    def setUp(self):
        self.region = RegionConfig.objects.create(
            code="RDY",
            name="Readiness Region",
            default_currency="USD",
            grading_scale="0-100",
        )
        CountryRegistry.objects.get_or_create(
            code="US",
            defaults={"name": "United States", "is_active": True},
        )
        self.school = School.objects.create(
            name="Readiness School",
            slug="readiness-school",
            subdomain="readiness-school",
            country_code="US",
            timezone="UTC",
            default_region=self.region,
            is_active=True,
        )

    def test_build_school_readiness_returns_phases(self):
        payload = build_school_readiness(self.school)
        self.assertTrue(payload.get("ok"))
        self.assertIn("phases", payload)
        self.assertEqual(len(payload["phases"]), 4)
        self.assertIn("provisioning_slo", payload)
        self.assertIn("meter_percent", payload)
        self.assertIn("needs_resume", payload["provision"])

    def test_needs_resume_surfaces_in_phases_and_slo(self):
        from apps.schools.tasks import _merge_provisioning_settings

        _merge_provisioning_settings(self.school, phase_a_complete=True)
        _merge_provisioning_settings(
            self.school, phase_b_failed_steps=["terms", "classrooms"]
        )
        self.school.save(update_fields=["settings", "updated_at"])
        payload = build_school_readiness(self.school)
        self.assertTrue(payload["provision"]["needs_resume"])
        self.assertEqual(
            payload["provision"]["phase_b_failed_steps"], ["classrooms", "terms"]
        )
        provision_phase = next(p for p in payload["phases"] if p["key"] == "provision")
        self.assertFalse(provision_phase["done"])
        self.assertEqual(payload["provisioning_slo"]["tone"], "warn")
