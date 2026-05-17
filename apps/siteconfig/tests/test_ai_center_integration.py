"""AI Center integration — plan §5.3 Phase C (rules-only guided endpoints)."""

from __future__ import annotations

import json
import os
import uuid
from unittest.mock import patch

from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django_otp.plugins.otp_totp.models import TOTPDevice

from apps.accounts.models import Permission, User
from apps.people.models import TeacherProfile
from apps.siteconfig.models import Plan
from apps.schools.models import School, SchoolMembership

_T_HOST = "aicenterint.runmycampus.com"


@override_settings(
    ALLOWED_HOSTS=["testserver", "127.0.0.1", "localhost", _T_HOST],
    AI_GATEWAY_ENABLED=True,
    AI_ALLOW_RULES_FALLBACK=True,
)
class AICenterIntegrationTests(TestCase):
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

    @classmethod
    def setUpTestData(cls):
        cls.plan = Plan.objects.create(name="Free", slug="basic", is_active=True)
        cls.school = School.objects.create(
            name="AI Center Integration School",
            slug="aicenterint",
            subdomain="aicenterint",
            is_active=True,
            plan=cls.plan,
        )
        cls.perm_settings, _ = Permission.objects.get_or_create(
            code="settings.manage",
            defaults={"name": "Manage settings"},
        )

    def _staff_client(self):
        u = User.objects.create_user(
            username=f"ai_int_{uuid.uuid4().hex[:8]}",
            password="x" * 8,
            role=User.Role.ADMIN,
            is_staff=True,
        )
        u.feature_permissions.add(self.perm_settings)
        SchoolMembership.objects.create(
            user=u,
            school=self.school,
            role=User.Role.ADMIN,
            is_primary=True,
        )
        TeacherProfile.objects.create(
            user=u,
            school=self.school,
            staff_id=f"AI{uuid.uuid4().hex[:4].upper()}",
        )
        TOTPDevice.objects.update_or_create(
            user=u, name="test-mfa", defaults={"confirmed": True}
        )
        c = Client(HTTP_HOST=_T_HOST)
        c.login(username=u.username, password="x" * 8)
        session = c.session
        session["school_id"] = str(self.school.id)
        session["mfa_verified"] = True
        session.save()
        return c

    @patch("apps.portal.views_ai_gateway.get_embedding_for_text", return_value=None)
    @patch("apps.portal.views_ai_gateway.AIMemoryService.search_similar", return_value=[])
    @patch("services.ai_gateway._call_ollama", return_value=(None, {"error": "unavailable"}))
    def test_representative_guided_endpoints_rules_mode_nonempty(
        self, _mock_ollama, _mock_search, _mock_emb
    ):
        client = self._staff_client()
        cases = (
            ("api:ai-interop-assistant", "Where is district interop configured?"),
            ("api:ai-studio-os-assistant", "How do I theme the portal shell?"),
            ("api:ai-observability-assistant", "Where do I check SLO dashboards?"),
            ("api:ai-trust-compliance-assistant", "What should we document for FERPA readiness?"),
        )
        for url_name, query in cases:
            with self.subTest(url_name=url_name):
                url = reverse(url_name, urlconf="config.tenant_urls")
                resp = client.post(
                    url,
                    data=json.dumps({"query": query}),
                    content_type="application/json",
                )
                self.assertEqual(resp.status_code, 200, resp.content)
                payload = resp.json()
                self.assertTrue(payload.get("success"), payload)
                summary = (payload.get("guided") or {}).get("summary") or ""
                self.assertGreater(len(summary), 40, summary)

        setup_url = reverse("api:ai-setup-assistant", urlconf="config.tenant_urls")
        setup_resp = client.post(
            setup_url,
            data=json.dumps({"query": "What should a new school enable first?"}),
            content_type="application/json",
        )
        self.assertEqual(setup_resp.status_code, 200, setup_resp.content)
        setup_payload = setup_resp.json()
        self.assertTrue(setup_payload.get("success"), setup_payload)
        setup_text = str(setup_payload.get("response") or "")
        self.assertGreater(len(setup_text), 20, setup_text)
