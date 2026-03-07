import json

from django.test import TestCase

from apps.accounts.models import User


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
