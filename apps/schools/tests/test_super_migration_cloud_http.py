"""HTTP tests for migration cloud Phase H + operator curated links (§11.4 batch 36)."""

import os
from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import User
from apps.platform_runtime.models import PlatformOperatorMigrationCloudLink


@override_settings(ALLOWED_HOSTS=["*"])
class SuperMigrationCloudHttpTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="super_migration_cloud_h",
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

    def test_migration_cloud_phase_h_skip_link_targets_main(self):
        url = reverse("super:migration_cloud")
        response = self.client.get(url, HTTP_HOST=self.host)
        self.assertEqual(response.status_code, 200)
        body = response.content.decode("utf-8")
        self.assertIn('href="#migration-cloud-main"', body)
        self.assertIn('id="migration-cloud-main"', body)

    def test_migration_cloud_renders_operator_curated_links(self):
        PlatformOperatorMigrationCloudLink.objects.create(
            slug="batch-36-registry",
            label="Open registry",
            href="/super/migration/registry/",
            sort_order=0,
        )
        url = reverse("super:migration_cloud")
        response = self.client.get(url, HTTP_HOST=self.host)
        self.assertEqual(response.status_code, 200)
        body = response.content.decode("utf-8")
        self.assertIn("Open registry", body)
        self.assertIn('href="/super/migration/registry/"', body)
