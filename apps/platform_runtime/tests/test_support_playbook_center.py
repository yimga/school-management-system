"""Support playbook center loads JSON registry and renders."""

import json
from pathlib import Path

from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import User


@override_settings(
    ALLOWED_HOSTS=["*"],
    MULTI_TENANT_BASE_DOMAIN="runmycampus.com",
)
class SupportPlaybookCenterTests(TestCase):
    def test_playbooks_json_loads(self):
        path = (
            Path(__file__).resolve().parent.parent
            / "data"
            / "support_playbooks.json"
        )
        data = json.loads(path.read_text(encoding="utf-8"))
        pbs = data.get("playbooks") or []
        self.assertGreaterEqual(len(pbs), 11)
        ids = {p["id"] for p in pbs}
        self.assertIn("payment_receipt_mismatch", ids)
        self.assertIn("offline_sync_conflicts", ids)
        self.assertIn("import_failure_quarantine", ids)
        self.assertTrue(all(p.get("expected_resolution_time") for p in pbs))

    def test_route_200_and_shape(self):
        User.objects.create_user(
            username="pb_super",
            password="x" * 8,
            is_superuser=True,
        )
        c = Client()
        self.assertTrue(c.login(username="pb_super", password="x" * 8))
        url = reverse("platform_runtime:support_playbook_center")
        r = c.get(url, HTTP_HOST="manager.runmycampus.com")
        self.assertEqual(r.status_code, 200)
        body = r.content.decode("utf-8", errors="replace")
        self.assertIn("severity", body.lower())
        self.assertIn("Owner role", body)
        self.assertIn("Expected resolution", body)
