from __future__ import annotations

import json
from pathlib import Path

from django.test import Client, TestCase, override_settings

from apps.accounts.models import User


ROOT = Path(__file__).resolve().parents[3]


class LowClickWorkflowAuditArtifactTests(TestCase):
    def test_workflow_click_reduction_audit_is_structured_and_no_overclaim(self):
        path = ROOT / "docs" / "generated" / "workflow_click_reduction_audit.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        self.assertIn("No 50% reduction claim", payload["claim_policy"])
        workflows = payload.get("workflows") or []
        self.assertGreaterEqual(len(workflows), 6)
        for row in workflows:
            self.assertTrue(row.get("workflow"))
            self.assertTrue(row.get("primary_action"))
            self.assertTrue(row.get("measurement_status"))
            self.assertIn("data", " ".join(row.get("data_hooks") or []))


@override_settings(
    ALLOWED_HOSTS=["*", "manager.runmycampus.com"],
    ROOT_URLCONF="config.urls",
)
class LowClickWorkflowRouteTests(TestCase):
    def test_manager_offline_sync_low_click_explainer_has_single_primary_path(self):
        User.objects.create_user(
            username="low_click_super",
            password="x" * 8,
            is_superuser=True,
        )
        client = Client(HTTP_HOST="manager.runmycampus.com")
        self.assertTrue(client.login(username="low_click_super", password="x" * 8))

        response = client.get("/offline/sync/", follow=True)
        self.assertEqual(response.status_code, 200)
        body = response.content.decode("utf-8", errors="replace")
        self.assertIn('data-action="offline-sync-select-tenant"', body)
        self.assertIn("tenant-scoped", body)
