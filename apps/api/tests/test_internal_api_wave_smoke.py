"""
Smoke: critical /api/internal/br/* paths return 2xx/4xx without 500 for staff + school_id.
"""

import json

from django.test import Client, TestCase
from django.urls import reverse

from apps.accounts.models import User
from apps.schools.models import School


class InternalApiWaveSmokeTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Smoke School",
            slug="smoke-school-audit",
            subdomain="smoke-school-audit",
            is_active=True,
        )
        self.staff = User.objects.create_user(
            username="staff_wave_smoke",
            email="sw@example.com",
            password="x",
            is_staff=True,
        )
        self.client = Client()
        self.assertTrue(
            self.client.login(username="staff_wave_smoke", password="x")
        )

    def _get(self, name, **extra):
        url = reverse(name)
        return self.client.get(url, **extra)

    def test_slo_targets_200(self):
        r = self._get("api:api-br-slo-targets")
        self.assertEqual(r.status_code, 200)
        self.assertIn(b"targets", r.content)

    def test_control_plane_bridge_manifest_403_staff_not_operator(self):
        """§2.1.1: manifest is control-plane only (not generic staff)."""
        r = self._get("api:api-control-plane-bridge-manifest")
        self.assertEqual(r.status_code, 403)

    def test_demographic_insights_with_school_id(self):
        r = self._get(
            "api:api-br-demographic-insights",
            data={"school_id": self.school.pk},
        )
        self.assertIn(r.status_code, (200, 400, 403))
        self.assertLess(r.status_code, 500)
        if r.status_code == 200:
            data = json.loads(r.content)
            self.assertIn("active_students", data)

    def test_climate_hooks_200(self):
        r = self._get("api:api-br-climate-hooks")
        self.assertEqual(r.status_code, 200)

    def test_rum_web_vitals_summary_200(self):
        r = self._get("api:api-north-star-rum-web-vitals")
        self.assertEqual(r.status_code, 200)
        data = json.loads(r.content)
        self.assertIn("beacon_count", data)
        self.assertIn("metrics", data)

    def test_upcoming_deadlines_with_school_id_no_500(self):
        base = reverse("api:api-north-star-upcoming-deadlines")
        r = self.client.get(f"{base}?school_id={self.school.pk}")
        self.assertLess(r.status_code, 500)
        self.assertEqual(r.status_code, 200)
        data = json.loads(r.content)
        self.assertIn("events", data)
        self.assertIn("version", data)
        self.assertIn("read_model", data)
        self.assertEqual(data.get("school_id"), str(self.school.pk))

    def test_migration_diff_preview_post(self):
        url = reverse("api:api-br-migration-diff")
        r = self.client.post(
            url,
            data=json.dumps({"csv_a": "a,b\n1,2", "csv_b": "a,b\n1,2"}),
            content_type="application/json",
        )
        self.assertIn(r.status_code, (200, 403))
        self.assertLess(r.status_code, 500)
