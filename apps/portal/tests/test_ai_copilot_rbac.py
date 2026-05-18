import json
import os
import uuid
from unittest.mock import patch

from django.test import Client, TestCase, override_settings

from apps.accounts.models import User
from apps.portal.views_ai_copilot import get_ai_permissions


class AiCopilotRbacTests(TestCase):
    def setUp(self):
        self.admin_user = User.objects.create_user(
            username="admin_ai",
            password="testpass123",
            role=User.Role.ADMIN,
        )
        self.teacher_user = User.objects.create_user(
            username="teacher_ai",
            password="testpass123",
            role=User.Role.TEACHER,
        )
        self.parent_user = User.objects.create_user(
            username="parent_ai",
            password="testpass123",
            role=User.Role.PARENT,
        )

    def test_ai_copilot_allows_admin_query(self):
        self.client.force_login(self.admin_user)
        response = self.client.post(
            "/api/ai-copilot/validate/",
            data=json.dumps({"query": "Show recent user activities"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload.get("success"))

    def test_ai_copilot_denies_teacher_financial_query(self):
        self.client.force_login(self.teacher_user)
        response = self.client.post(
            "/api/ai-copilot/validate/",
            data=json.dumps({"query": "Show outstanding invoices"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 403)
        payload = response.json()
        self.assertFalse(payload.get("success"))

    def test_ai_copilot_allows_parent_fee_query(self):
        self.client.force_login(self.parent_user)
        response = self.client.post(
            "/api/ai-copilot/validate/",
            data=json.dumps({"query": "Show my fee payment status"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload.get("success"))

    def test_superadmin_without_django_superuser_gets_admin_scope(self):
        u = User.objects.create_user(
            username=f"sa_copilot_{uuid.uuid4().hex[:8]}",
            password="testpass123",
            role=User.Role.SUPERADMIN,
            is_staff=False,
            is_superuser=False,
        )
        perms = get_ai_permissions(u)
        self.assertEqual(perms["scope"], "admin")
        self.assertTrue(perms["can_view_compliance"])


_MGR = "manager.runmycampus.com"


@override_settings(
    ALLOWED_HOSTS=["testserver", "127.0.0.1", "localhost", _MGR],
    ROOT_URLCONF="config.manager_urls",
)
class AiCopilotManagerHostTests(TestCase):
    databases = {"default"}

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._cp_roles_patch = patch.dict(
            os.environ, {"CONTROL_PLANE_OPERATOR_ROLES": "SUPERADMIN"}, clear=False
        )
        cls._cp_roles_patch.start()

    @classmethod
    def tearDownClass(cls):
        cls._cp_roles_patch.stop()
        super().tearDownClass()

    @patch("apps.portal.views_ai_copilot.generate_ai_response")
    def test_manager_superadmin_can_post_copilot_query(self, mock_gen):
        mock_gen.return_value = ("Here are three improvements to verify.", {"provider": "rules"})
        u = User.objects.create_user(
            username=f"mgr_copilot_{uuid.uuid4().hex[:8]}",
            password="testpass123",
            role=User.Role.SUPERADMIN,
            is_staff=False,
            is_superuser=False,
        )
        c = Client(HTTP_HOST=_MGR)
        c.login(username=u.username, password="testpass123")
        resp = c.post(
            "/api/ai-copilot/validate/",
            data=json.dumps({"query": "What can we improve in automation?"}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200, resp.content[:400])
        self.assertTrue(resp.json().get("success"))
