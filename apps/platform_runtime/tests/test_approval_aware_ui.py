from __future__ import annotations

from django.test import Client, TestCase, override_settings

from apps.accounts.models import User
from apps.platform_runtime.models import ConfigurationChangeRequest
from apps.schools.models import School
from apps.test_utils.http_clients import login_manager_client


@override_settings(ALLOWED_HOSTS=["*", "manager.runmycampus.com"], ROOT_URLCONF="config.urls")
class ApprovalAwareUITests(TestCase):
    def setUp(self):
        self.school = School.objects.create(name="Approval UI", slug="approval-ui", subdomain="approval-ui", is_active=True)
        self.operator = User.objects.create_user(username="approval_ui_operator", password="x" * 8, role=User.Role.SUPERADMIN, is_staff=True, is_superuser=True)

    def test_high_risk_pack_page_shows_request_approval(self):
        # Manager-host operator page: needs confirmed device + verified MFA on a
        # manager-bound session (a bare client.login bounces 302 to MFA setup).
        client = login_manager_client(self.operator, password="x" * 8)

        response = client.get(f"/configuration/dashboard-packs/network-operator/apply/?school={self.school.slug}")

        self.assertEqual(response.status_code, 200, msg=response.content[:500])
        self.assertIn("Request approval", response.content.decode("utf-8", errors="replace"))

    def test_post_creates_change_request(self):
        # Manager-host operator page: needs confirmed device + verified MFA on a
        # manager-bound session (a bare client.login bounces 302 to MFA setup).
        client = login_manager_client(self.operator, password="x" * 8)

        response = client.post(f"/configuration/dashboard-packs/network-operator/apply/?school={self.school.slug}", {"action": "request_approval", "reason": "Night rollout"})

        self.assertEqual(response.status_code, 302)
        self.assertTrue(ConfigurationChangeRequest.objects.filter(school=self.school, target_key="network-operator").exists())
