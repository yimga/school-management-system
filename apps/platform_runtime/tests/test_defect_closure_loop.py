from __future__ import annotations

from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import User
from apps.platform_runtime.models import PilotDefect


@override_settings(ALLOWED_HOSTS=["*"], MULTI_TENANT_BASE_DOMAIN="runmycampus.com")
class DefectClosureLoopContractTests(TestCase):
    def test_defect_closure_loop_dashboard_requires_proof_for_fixed_items(self):
        PilotDefect.objects.create(
            title="Receipt mismatch regression",
            source_school_slug="pilot-cm-001",
            severity=PilotDefect.Severity.CRITICAL,
            module="finance",
            owner="support",
            status=PilotDefect.Status.FIXED,
            sot_batch="product-domination",
        )
        User.objects.create_user(
            username="defect_closure_super",
            password="x" * 8,
            is_superuser=True,
        )
        client = Client()
        self.assertTrue(client.login(username="defect_closure_super", password="x" * 8))

        response = client.get(
            reverse("platform_runtime:pilot_defect_dashboard"),
            HTTP_HOST="manager.runmycampus.com",
        )
        self.assertEqual(response.status_code, 200)
        body = response.content.decode("utf-8", errors="replace")
        self.assertIn("Fixes without proof", body)
        self.assertIn("Receipt mismatch regression", body)
        self.assertIn("product-domination", body)
