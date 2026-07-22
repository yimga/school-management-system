"""PGL-009 — signup vs CLI vs API initial school.settings parity."""

from __future__ import annotations

from unittest.mock import patch

from django.test import SimpleTestCase, TestCase

from apps.schools.models import School
from apps.schools.school_settings_seed import (
    build_initial_school_settings,
    resolve_school_geo_create_fields,
)


class SchoolSettingsSeedParityTests(SimpleTestCase):
    def test_cli_and_signup_share_localization_and_governance_keys(self):
        signup = build_initial_school_settings(
            country_code="NG",
            school_type_code="sss",
            language_code="en",
            seed_marker="_seeded_at_signup",
        )
        cli = build_initial_school_settings(
            country_code="NG",
            school_type_code="sss",
            language_code="en",
            seed_marker="_seeded_by_create_school_command",
        )
        for key in (
            "country_code",
            "calendar_code",
            "school_type_code",
            "language_code",
            "primary_language_code",
        ):
            self.assertEqual(signup["localization"][key], cli["localization"][key], key)
        self.assertIn("governance", signup)
        self.assertIn("governance", cli)
        self.assertTrue(signup["localization"]["_seeded_at_signup"])
        self.assertTrue(cli["localization"]["_seeded_by_create_school_command"])

    def test_geo_fields_include_compliance_region(self):
        geo = resolve_school_geo_create_fields("US")
        self.assertEqual(geo["compliance_region"], "US")
        self.assertIn("timezone", geo)
        self.assertIn("currency", geo)


class CreateSchoolCommandSettingsTests(TestCase):
    def test_create_school_command_uses_rich_seed(self):
        from apps.schools.management.commands.create_school import Command

        cmd = Command()
        school, created = cmd._get_or_create_school(
            School,
            name="Parity High",
            slug="parity-high-ng",
            country="NG",
            school_type="sss",
        )
        self.assertTrue(created)
        loc = (school.settings or {}).get("localization") or {}
        self.assertEqual(loc.get("country_code"), "NG")
        self.assertEqual(loc.get("school_type_code"), "sss")
        self.assertTrue(loc.get("_seeded_by_create_school_command"))
        self.assertIn("calendar_code", loc)
        self.assertIn("governance", school.settings or {})
        self.assertEqual(school.compliance_region, "NDPR")


class ApiCreateSchoolSettingsParityTests(TestCase):
    def test_api_create_school_seeds_localization_and_geo(self):
        import json

        from django.contrib.auth import get_user_model
        from django.test import RequestFactory

        from apps.schools.super_views_provisioning import api_create_school

        User = get_user_model()
        user = User.objects.create_superuser(
            username="api-seed-admin",
            email="api-seed-admin@example.com",
            password="TestPass123!",
        )
        factory = RequestFactory()
        payload = {
            "name": "API Seed Academy",
            "slug": "api-seed-academy-ng",
            "contact_email": "owner@api-seed.test",
            "country_code": "NG",
            "school_type_code": "sss",
            "language_code": "en",
        }
        request = factory.post(
            "/super/api/create-school/",
            data=json.dumps(payload),
            content_type="application/json",
        )
        request.user = user
        with patch(
            "apps.schools.tasks.complete_provisioning_for_school",
            return_value={
                "queued": False,
                "job_id": None,
                "fallback": True,
                "message": "test-skip-provision",
            },
        ):
            response = api_create_school(request)
        self.assertIn(response.status_code, (200, 201, 202), response.content)
        school = School.objects.get(slug="api-seed-academy-ng")
        loc = (school.settings or {}).get("localization") or {}
        self.assertEqual(loc.get("country_code"), "NG")
        self.assertEqual(loc.get("school_type_code"), "sss")
        self.assertTrue(loc.get("_seeded_at_api_create_school"))
        self.assertIn("governance", school.settings or {})
        self.assertTrue(school.compliance_region)
        self.assertTrue(school.timezone)
