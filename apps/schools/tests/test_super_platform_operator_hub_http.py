"""HTTP tests for platform operator hub Phase H + operator curated links (batch 35 #436 / #449)."""

import os
from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import User
from apps.platform_runtime.models import PlatformOperatorPlatformHubLink


@override_settings(ALLOWED_HOSTS=["*"])
class SuperPlatformOperatorHubHttpTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="super_platform_op_hub_h",
            password="testpass123",
            is_staff=True,
            is_superuser=True,
        )
        self.client.force_login(self.user)
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

    def test_platform_operator_hub_phase_h_skip_link_targets_main(self):
        url = reverse("super:platform_operator_hub")
        response = self.client.get(url, HTTP_HOST=self.host)
        self.assertEqual(response.status_code, 200)
        body = response.content.decode("utf-8")
        self.assertIn('href="#platform-operator-hub-main"', body)
        self.assertIn('id="platform-operator-hub-main"', body)

    def test_platform_operator_hub_renders_operator_platform_hub_curated_links(self):
        PlatformOperatorPlatformHubLink.objects.create(
            slug="batch-35-pulse",
            label="Open pulse",
            href="/super/pulse/",
            sort_order=0,
        )
        url = reverse("super:platform_operator_hub")
        response = self.client.get(url, HTTP_HOST=self.host)
        self.assertEqual(response.status_code, 200)
        body = response.content.decode("utf-8")
        self.assertIn("Open pulse", body)
        self.assertIn('href="/super/pulse/"', body)
