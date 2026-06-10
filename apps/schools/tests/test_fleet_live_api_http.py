"""HTTP tests for fleet live JSON API."""
import os
from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import User, UserPasskey
from apps.platform_runtime.operator_identity import ensure_platform_operator_profile
from apps.schools.models import School
from apps.schools.tests.manager_client import login_manager_control_plane


@override_settings(ALLOWED_HOSTS=["*"])
class FleetLiveApiHttpTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="fleet_live_api",
            password="testpass123",
            is_staff=True,
            is_superuser=True,
            role=User.Role.SUPERADMIN,
        )
        ensure_platform_operator_profile(self.user, tier="break_glass")
        UserPasskey.objects.create(
            user=self.user,
            name="Fleet live test passkey",
            credential_id="fleet-live-test-passkey",
            public_key="test-public-key",
        )
        self.client.force_login(self.user)
        login_manager_control_plane(self.client, self.user, password="testpass123")
        self.host = "manager.runmycampus.com"
        cache.clear()
        self.env = patch.dict(
            os.environ,
            {
                "MULTI_TENANT_BASE_DOMAIN": "runmycampus.com",
                "MULTI_TENANT_LEGACY_BASE_DOMAINS": "",
            },
            clear=False,
        )
        self.env.start()
        School.objects.create(
            name="Fleet Live School",
            slug="fleet-live-school",
            subdomain="fleet-live-school",
            is_active=True,
            is_approved=True,
        )

    def tearDown(self):
        self.env.stop()

    def test_fleet_live_json_returns_summary_and_rows(self):
        url = reverse("super:api_fleet_live")
        response = self.client.get(url, HTTP_HOST=self.host)
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("summary", payload)
        self.assertIn("rows", payload)
        self.assertIn("revision", payload)
        self.assertGreaterEqual(payload["summary"].get("total", 0), 1)
        self.assertEqual(payload.get("poll_interval_seconds"), 15)

    def test_fleet_stream_returns_event_stream(self):
        url = reverse("super:api_fleet_stream")
        response = self.client.get(url, HTTP_HOST=self.host)
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/event-stream", response["Content-Type"])

    def test_cockpit_live_json_includes_fleet_heatmap(self):
        url = reverse("super:api_cockpit_live")
        response = self.client.get(url, HTTP_HOST=self.host)
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        heatmap = payload.get("tenant_heatmap") or {}
        self.assertIn("tiles", heatmap)
        self.assertIn("fleet_summary", heatmap)
        self.assertIn("revision", heatmap)
