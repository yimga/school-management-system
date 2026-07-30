"""HTTP tests for super command center (Phase H + operator curated links)."""

import os
from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import User
from apps.platform_runtime.models import PlatformOperatorCommandCenterLink
from apps.test_utils.http_clients import login_manager_client


@override_settings(ALLOWED_HOSTS=["*"])
class SuperCommandCenterHttpTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="super_command_center_h",
            password="testpass123",
            is_staff=True,
            is_superuser=True,
        )
        # Manager-host operator page: bind the manager session with confirmed +
        # verified MFA (bare force_login bounces 302 through RequireMFAMiddleware).
        self.client = login_manager_client(self.user, password="testpass123")
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

    def tearDown(self):
        self.env.stop()

    def test_command_center_phase_h_skip_link_targets_main(self):
        url = reverse("super:command_center")
        response = self.client.get(url, HTTP_HOST=self.host)
        self.assertEqual(response.status_code, 200)
        body = response.content.decode("utf-8")
        self.assertIn('href="#command-center-main"', body)
        self.assertIn('id="command-center-main"', body)

    def test_command_center_renders_operator_command_center_curated_links(self):
        PlatformOperatorCommandCenterLink.objects.create(
            slug="batch-31-pulse",
            label="Open pulse from CC",
            href="/super/pulse/",
            sort_order=0,
        )
        url = reverse("super:command_center")
        response = self.client.get(url, HTTP_HOST=self.host)
        self.assertEqual(response.status_code, 200)
        body = response.content.decode("utf-8")
        self.assertIn("Open pulse from CC", body)
        self.assertIn('href="/super/pulse/"', body)
