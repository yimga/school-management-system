"""HTTP tests for /api/ai/* guided domain assistants."""

import json
import os
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.schools.models import School

User = get_user_model()


@override_settings(ALLOWED_HOSTS=["*"])
@patch.dict(os.environ, {"MULTI_TENANT_BASE_DOMAIN": "example.com"}, clear=False)
class GuidedAssistantAPITests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="AI Test School",
            slug="ai-test",
            subdomain="ai-test",
            is_active=True,
        )
        self.admin = User.objects.create_user(username="ga_admin", password="x")
        self.admin.role = User.Role.ADMIN
        self.admin.save(update_fields=["role"])
        # Platform operator: observability is an operator tool, so the user must
        # be a genuine control-plane operator (superuser) — bare is_staff is
        # intentionally NOT sufficient to cross onto a tenant host
        # (TenantHostMembershipMiddleware), so it would be redirected (302).
        self.staff = User.objects.create_user(username="ga_staff", password="x")
        self.staff.is_staff = True
        self.staff.is_superuser = True
        self.staff.save(update_fields=["is_staff", "is_superuser"])

    def _client(self, user):
        c = Client(HTTP_HOST="ai-test.example.com")
        c.force_login(user)
        return c

    @patch("apps.portal.views_ai_gateway._gateway_response")
    @patch("apps.portal.views_ai_gateway._check_rate_limit")
    @patch("apps.portal.views_ai_gateway._log_gateway_audit")
    def test_interop_assistant_tenant_admin_ok(self, _audit, mock_rl, mock_gw):
        mock_rl.return_value = (True, 0)
        mock_gw.return_value = (
            {
                "summary": "ok",
                "actions": [{"title": "a", "detail": "b"}],
                "cautions": [],
                "references": [],
            },
            {"provider": "rules"},
        )
        c = self._client(self.admin)
        r = c.post(
            reverse("api:ai-interop-assistant"),
            data=json.dumps({"query": "How do I test LTI?"}),
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 200)
        data = json.loads(r.content)
        self.assertTrue(data["success"])
        self.assertEqual(data["guided"]["summary"], "ok")

    def test_observability_denied_for_tenant_admin(self):
        c = self._client(self.admin)
        r = c.post(
            reverse("api:ai-observability-assistant"),
            data=json.dumps({"query": "SLO?"}),
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 403)

    @patch("apps.portal.views_ai_gateway._gateway_response")
    @patch("apps.portal.views_ai_gateway._check_rate_limit")
    @patch("apps.portal.views_ai_gateway._log_gateway_audit")
    def test_observability_staff_ok(self, _audit, mock_rl, mock_gw):
        mock_rl.return_value = (True, 0)
        mock_gw.return_value = (
            {
                "summary": "s",
                "actions": [],
                "cautions": [],
                "references": [],
            },
            {"provider": "rules"},
        )
        c = Client(HTTP_HOST="ai-test.example.com")
        c.force_login(self.staff)
        r = c.post(
            reverse("api:ai-observability-assistant"),
            data=json.dumps({"query": "health endpoints?"}),
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 200)
