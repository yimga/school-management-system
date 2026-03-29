"""HTTP tests for super tenant health monitor (Phase H + operator curated links)."""

import os
from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import User
from apps.platform_runtime.models import PlatformOperatorTenantHealthLink
from apps.schools.models import School


@override_settings(ALLOWED_HOSTS=["*"])
class SuperTenantHealthHttpTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="super_tenant_health_h",
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
        School.objects.create(
            name="Health School",
            slug="health-school",
            subdomain="health-school",
            is_active=True,
        )

    def tearDown(self):
        self.env.stop()

    def test_tenant_health_phase_h_skip_link_targets_main(self):
        url = reverse("super:tenant_health")
        response = self.client.get(url, HTTP_HOST=self.host)
        self.assertEqual(response.status_code, 200)
        body = response.content.decode("utf-8")
        self.assertIn('href="#tenant-health-main"', body)
        self.assertIn('id="tenant-health-main"', body)

    def test_tenant_health_renders_operator_tenant_health_curated_links(self):
        PlatformOperatorTenantHealthLink.objects.create(
            slug="batch-30-pulse",
            label="Open pulse map",
            href="/super/pulse/",
            sort_order=0,
        )
        url = reverse("super:tenant_health")
        response = self.client.get(url, HTTP_HOST=self.host)
        self.assertEqual(response.status_code, 200)
        body = response.content.decode("utf-8")
        self.assertIn("Open pulse map", body)
        self.assertIn('href="/super/pulse/"', body)
