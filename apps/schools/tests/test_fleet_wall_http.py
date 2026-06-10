"""HTTP tests for fleet wall operator surface."""
from __future__ import annotations

import itertools
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
class FleetWallHttpTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="fleet_wall_api",
            password="testpass123",
            is_staff=True,
            is_superuser=True,
            role=User.Role.SUPERADMIN,
        )
        ensure_platform_operator_profile(self.user, tier="break_glass")
        UserPasskey.objects.create(
            user=self.user,
            name="Fleet wall test passkey",
            credential_id="fleet-wall-test-passkey",
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
            name="Fleet Wall HTTP School",
            slug="fleet-wall-http-school",
            subdomain="fleet-wall-http-school",
            is_active=True,
            is_approved=True,
        )

    def tearDown(self):
        self.env.stop()

    def test_fleet_wall_page_renders(self):
        url = reverse("super:fleet_wall")
        response = self.client.get(url, HTTP_HOST=self.host)
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn('data-rmc-fleet-wall="1"', content)
        self.assertIn("rmc-fleet-wall.js", content)

    def test_fleet_wall_stream_mode_returns_event_stream(self):
        url = reverse("super:api_fleet_stream") + "?mode=wall&chunk_size=25"
        response = self.client.get(url, HTTP_HOST=self.host)
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/event-stream", response["Content-Type"])
        body = b"".join(itertools.islice(response.streaming_content, 8)).decode()
        self.assertIn('"type": "summary"', body)
        self.assertIn('"type": "chunk"', body)
        self.assertIn('"type": "wall_ready"', body)
