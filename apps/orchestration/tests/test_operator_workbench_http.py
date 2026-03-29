"""HTTP tests for orchestration operator workbench (Phase H + operator curated links)."""

import os
from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import User
from apps.platform_runtime.models import PlatformOperatorOrchestrationWorkbenchLink


@override_settings(ALLOWED_HOSTS=["*"])
class OperatorWorkbenchHttpTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="orch_workbench_h",
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

    def test_workbench_phase_h_skip_link_targets_main(self):
        url = reverse("super:orchestration_workbench")
        response = self.client.get(url, HTTP_HOST=self.host)
        self.assertEqual(response.status_code, 200)
        body = response.content.decode("utf-8")
        self.assertIn('href="#orchestration-workbench-main"', body)
        self.assertIn('id="orchestration-workbench-main"', body)

    def test_workbench_renders_operator_orchestration_curated_links(self):
        PlatformOperatorOrchestrationWorkbenchLink.objects.create(
            slug="batch-32-playbook",
            label="Open playbook hub",
            href="/super/playbook-operator-hub/",
            sort_order=0,
        )
        url = reverse("super:orchestration_workbench")
        response = self.client.get(url, HTTP_HOST=self.host)
        self.assertEqual(response.status_code, 200)
        body = response.content.decode("utf-8")
        self.assertIn("Open playbook hub", body)
        self.assertIn('href="/super/playbook-operator-hub/"', body)
