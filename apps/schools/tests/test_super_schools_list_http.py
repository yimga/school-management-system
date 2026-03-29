"""HTTP tests for super schools list Phase H + operator curated links (batch 34 #421 / #432)."""

import os
from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import User
from apps.platform_runtime.models import PlatformOperatorSuperSchoolsListLink


@override_settings(ALLOWED_HOSTS=["*"])
class SuperSchoolsListHttpTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="super_schools_list_h",
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

    def test_schools_list_phase_h_skip_link_targets_main(self):
        url = reverse("super:schools_list")
        response = self.client.get(url, HTTP_HOST=self.host)
        self.assertEqual(response.status_code, 200)
        body = response.content.decode("utf-8")
        self.assertIn('href="#super-schools-list-main"', body)
        self.assertIn('id="super-schools-list-main"', body)

    def test_schools_list_renders_operator_super_schools_list_curated_links(self):
        PlatformOperatorSuperSchoolsListLink.objects.create(
            slug="batch-34-tenant-health",
            label="Open tenant health",
            href="/super/tenant-health/",
            sort_order=0,
        )
        url = reverse("super:schools_list")
        response = self.client.get(url, HTTP_HOST=self.host)
        self.assertEqual(response.status_code, 200)
        body = response.content.decode("utf-8")
        self.assertIn("Open tenant health", body)
        self.assertIn('href="/super/tenant-health/"', body)
