"""HTTP tests for super analytics overview Phase H + operator curated links (batch 35 #436 / #447)."""

import os
from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import User
from apps.platform_runtime.models import PlatformOperatorSuperAnalyticsOverviewLink


@override_settings(ALLOWED_HOSTS=["*"])
class SuperAnalyticsOverviewHttpTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="super_analytics_overview_h",
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

    def test_analytics_overview_phase_h_skip_link_targets_main(self):
        url = reverse("super:analytics_overview")
        response = self.client.get(url, HTTP_HOST=self.host)
        self.assertEqual(response.status_code, 200)
        body = response.content.decode("utf-8")
        self.assertIn('href="#analytics-overview-main"', body)
        self.assertIn('id="analytics-overview-main"', body)

    def test_analytics_overview_renders_operator_curated_links(self):
        PlatformOperatorSuperAnalyticsOverviewLink.objects.create(
            slug="batch-35-usage",
            label="Open usage",
            href="/super/usage/",
            sort_order=0,
        )
        url = reverse("super:analytics_overview")
        response = self.client.get(url, HTTP_HOST=self.host)
        self.assertEqual(response.status_code, 200)
        body = response.content.decode("utf-8")
        self.assertIn("Open usage", body)
        self.assertIn('href="/super/usage/"', body)
