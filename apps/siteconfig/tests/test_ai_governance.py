"""AI governance tenant page (authorized users; no secrets in body)."""

from __future__ import annotations

import uuid

from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import Permission, User
from apps.people.models import TeacherProfile
from apps.siteconfig.ai_assistants import assistant_keys
from apps.siteconfig.models import Plan
from apps.schools.models import School

_T_HOST = "aigov.runmycampus.com"


@override_settings(ALLOWED_HOSTS=["testserver", "127.0.0.1", "localhost", _T_HOST])
class AIGovernancePageTests(TestCase):
    databases = {"default"}

    @classmethod
    def setUpTestData(cls):
        cls.plan = Plan.objects.create(name="Free", slug="basic", is_active=True)
        cls.school = School.objects.create(
            name="AI Gov School",
            slug="aigov",
            subdomain="aigov",
            is_active=True,
            plan=cls.plan,
        )
        cls.perm_settings, _ = Permission.objects.get_or_create(
            code="settings.manage",
            defaults={"name": "Manage settings"},
        )

    def test_registry_has_required_assistants(self):
        keys = assistant_keys()
        for req in (
            "config_copilot",
            "workflow_builder_assistant",
            "report_comment_assistant",
            "onboarding_assistant",
            "support_assistant",
            "data_quality_assistant",
            "trust_compliance_assistant",
            "studio_os_assistant",
        ):
            self.assertIn(req, keys)

    def test_authorized_user_renders_governance(self):
        u = User.objects.create_user(
            username=f"ai_gov_{uuid.uuid4().hex[:8]}",
            password="x" * 8,
            role=User.Role.ADMIN,
            is_staff=True,
        )
        u.feature_permissions.add(self.perm_settings)
        TeacherProfile.objects.create(user=u, school=self.school, staff_id="AG1")
        c = Client(HTTP_HOST=_T_HOST)
        c.login(username=u.username, password="x" * 8)
        path = reverse("siteconfig:ai_governance", urlconf="config.tenant_urls")
        resp = c.get(path)
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode("utf-8", errors="replace")
        self.assertIn("data-shell-surface", body)
        self.assertIn("AI governance", body)
        self.assertNotIn("sk_", body)
        self.assertNotIn("api.openai.com", body.lower())

    def test_unauthorized_blocked(self):
        u = User.objects.create_user(
            username="no_ai_gov",
            password="x" * 8,
            role=User.Role.TEACHER,
        )
        TeacherProfile.objects.create(user=u, school=self.school, staff_id="AG2")
        c = Client(HTTP_HOST=_T_HOST)
        c.login(username="no_ai_gov", password="x" * 8)
        path = reverse("siteconfig:ai_governance", urlconf="config.tenant_urls")
        resp = c.get(path)
        self.assertIn(resp.status_code, (302, 403))
