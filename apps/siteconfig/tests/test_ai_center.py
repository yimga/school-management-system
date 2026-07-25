"""AI Center: unified governed-assistant surface."""

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
from apps.siteconfig.ai_assistants import assistant_keys, get_assistant
from apps.siteconfig.models import Plan
from apps.schools.models import School, SchoolMembership
from apps.test_utils.http_clients import login_manager_client

_T_HOST = "aicenter.runmycampus.com"


@override_settings(ALLOWED_HOSTS=["testserver", "127.0.0.1", "localhost", _T_HOST], LITELLM_PROXY_URL="")
class AICenterPageTests(TestCase):
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
            name="AI Center School",
            slug="aicenter",
            subdomain="aicenter",
            is_active=True,
            plan=cls.plan,
        )
        cls.perm_settings, _ = Permission.objects.get_or_create(
            code="settings.manage",
            defaults={"name": "Manage settings"},
        )

    def _staff_user(self, *, role=User.Role.ADMIN):
        u = User.objects.create_user(
            username=f"ai_center_{uuid.uuid4().hex[:8]}",
            password="x" * 8,
            role=role,
            is_staff=True,
        )
        u.feature_permissions.add(self.perm_settings)
        SchoolMembership.objects.create(
            user=u,
            school=self.school,
            role=str(role),
            is_primary=True,
        )
        TeacherProfile.objects.create(
            user=u, school=self.school, staff_id=f"AC{uuid.uuid4().hex[:4].upper()}"
        )
        TOTPDevice.objects.update_or_create(
            user=u, name="test-mfa", defaults={"confirmed": True}
        )
        return u

    def _staff_client(self, **user_kwargs):
        u = self._staff_user(**user_kwargs)
        c = Client(HTTP_HOST=_T_HOST)
        c.login(username=u.username, password="x" * 8)
        session = c.session
        session["school_id"] = str(self.school.id)
        session["mfa_verified"] = True
        session.save()
        return c, u

    def test_registry_includes_observability_and_billing(self):
        keys = assistant_keys()
        for req in ("observability_assistant", "billing_usage_explain"):
            self.assertIn(req, keys, f"AI Center needs {req!r} in registry")

    def test_every_registry_row_has_api_url_name_and_hint(self):
        for key in assistant_keys():
            row = get_assistant(key)
            self.assertIsNotNone(row, key)
            self.assertTrue(row.get("api_url_name"), f"{key} missing api_url_name")
            self.assertTrue(row.get("hint"), f"{key} missing hint")

    def test_authenticated_user_renders_ai_center(self):
        c, _u = self._staff_client()
        path = reverse("siteconfig:ai_center", urlconf="config.tenant_urls")
        resp = c.get(path)
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode("utf-8", errors="replace")
        self.assertIn("AI Center", body)
        self.assertIn("data-rmc-ai-center", body)
        self.assertIn("data-rmc-ai-transcript", body)
        self.assertIn("data-rmc-ai-health-root", body)
        self.assertIn("api/ai/health/", body)
        self.assertIn("data-rmc-ai-browser-offline", body)
        self.assertIn("Observability &amp; SLO assistant", body)
        self.assertIn("Billing &amp; usage explainer", body)
        self.assertIn("Trust &amp; compliance assistant", body)
        self.assertNotIn("sk_", body)

    def test_focus_query_preselects_assistant(self):
        c, _u = self._staff_client()
        path = reverse("siteconfig:ai_center", urlconf="config.tenant_urls")
        resp = c.get(path + "?focus=billing_usage_explain")
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode("utf-8", errors="replace")
        self.assertIn("Billing &amp; usage explainer", body)
        self.assertIn("aria-selected=\"true\"", body)

    def test_staff_sees_operator_ai_setup(self):
        c, _u = self._staff_client()
        path = reverse("siteconfig:ai_center", urlconf="config.tenant_urls")
        resp = c.get(path)
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode("utf-8", errors="replace")
        self.assertIn("data-rmc-ai-health-root", body)
        self.assertIn("Gateway tiers", body)
        self.assertIn("LITELLM_PROXY_URL", body)
        self.assertIn("Render SaaS cloud AI", body)

    @override_settings(RMC_DEPLOYMENT_PROFILE="edge")
    def test_staff_sees_edge_ollama_operator_block(self):
        c, _u = self._staff_client()
        path = reverse("siteconfig:ai_center", urlconf="config.tenant_urls")
        resp = c.get(path)
        body = resp.content.decode("utf-8", errors="replace")
        self.assertIn("ollama serve", body)
        self.assertIn("RMC_DEPLOYMENT_PROFILE=edge", body)

    def test_anonymous_redirects_to_login(self):
        c = Client(HTTP_HOST=_T_HOST)
        path = reverse("siteconfig:ai_center", urlconf="config.tenant_urls")
        resp = c.get(path)
        self.assertIn(resp.status_code, (302, 401, 403))

    def test_ai_center_in_cmdk_payload(self):
        c, _u = self._staff_client()
        resp = c.get("/")
        if resp.status_code != 200:
            return
        body = resp.content.decode("utf-8", errors="replace")
        if "rmc-cmdk-data" in body:
            self.assertIn("AI Center", body)

    @patch("apps.portal.views_ai_gateway.get_embedding_for_text", return_value=None)
    @patch("apps.portal.views_ai_gateway.AIMemoryService.search_similar", return_value=[])
    @patch("services.ai_gateway._call_ollama", return_value=(None, {"error": "unavailable"}))
    def test_ai_center_interop_post_rules_mode_nonempty(
        self, _mock_ollama, _mock_search, _mock_emb
    ):
        import json

        c, _u = self._staff_client()
        url = reverse("api:ai-interop-assistant", urlconf="config.tenant_urls")
        resp = c.post(
            url,
            data=json.dumps({"query": "Where is district interop configured?"}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        payload = resp.json()
        self.assertTrue(payload.get("success"))
        summary = (payload.get("guided") or {}).get("summary") or ""
        self.assertGreater(len(summary), 40, summary)


_MGR_HOST = "manager.runmycampus.com"


@override_settings(
    ALLOWED_HOSTS=["testserver", "127.0.0.1", "localhost", _MGR_HOST],
    ROOT_URLCONF="config.manager_urls",
    LITELLM_PROXY_URL="",
)
class AICenterManagerControlPlaneTests(TestCase):
    databases = {"default"}

    def test_manager_ai_center_uses_control_plane_shell(self):
        u = User.objects.create_user(
            username="mgr_ai_center",
            password="x" * 8,
            is_staff=True,
            is_superuser=True,
        )
        c = Client(HTTP_HOST=_MGR_HOST)
        c.login(username=u.username, password="x" * 8)
        path = reverse("siteconfig:ai_center", urlconf="config.manager_urls")
        self.assertIn("/siteconfig/ai-center/", path)
        resp = c.get(path)
        self.assertEqual(resp.status_code, 200, msg=getattr(resp, "content", b"")[:500])
        body = resp.content.decode("utf-8", errors="replace")
        self.assertIn('data-rmc-os-shell="control-plane"', body)
        self.assertIn('id="cp-main-content"', body)
        self.assertIn("data-rmc-ai-center", body)
        self.assertNotIn("Hreflang: emits per-locale", body)

    def test_manager_registry_api_urls_resolve(self):
        """AI Center on manager must bind assistants to /api/ai/* (not empty api_url)."""
        for key in assistant_keys():
            row = get_assistant(key)
            self.assertIsNotNone(row, key)
            name = row.get("api_url_name") or ""
            self.assertTrue(name, f"{key} missing api_url_name")
            url = reverse(name, urlconf="config.manager_urls")
            self.assertTrue(
                url.startswith("/api/"),
                f"{key} resolved to {url!r}, expected /api/ prefix",
            )

    def test_manager_ai_center_assistants_have_api_urls_in_html(self):
        u = User.objects.create_user(
            username=f"mgr_ai_urls_{uuid.uuid4().hex[:8]}",
            password="x" * 8,
            is_staff=True,
            is_superuser=True,
        )
        c = Client(HTTP_HOST=_MGR_HOST)
        c.login(username=u.username, password="x" * 8)
        path = reverse("siteconfig:ai_center", urlconf="config.manager_urls")
        resp = c.get(path)
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode("utf-8", errors="replace")
        self.assertIn('data-api-url="/api/ai/', body)
        self.assertNotIn('data-api-url=""', body)

    def test_manager_superadmin_role_without_django_superuser_can_use_assistants(self):
        """Control-plane operators often have role=SUPERADMIN but is_superuser=False."""
        u = User.objects.create_user(
            username=f"mgr_superadmin_{uuid.uuid4().hex[:8]}",
            password="x" * 8,
            is_staff=True,
            is_superuser=False,
            role=User.Role.SUPERADMIN,
        )
        # role=SUPERADMIN arms strict operator MFA on the manager host;
        # login_manager_client gives a confirmed device + verified manager
        # session so the assistants page renders instead of bouncing to setup.
        c = login_manager_client(u, password="x" * 8)
        path = reverse("siteconfig:ai_center", urlconf="config.manager_urls")
        resp = c.get(path)
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode("utf-8", errors="replace")
        self.assertIn('data-api-url="/api/ai/', body)
        self.assertNotIn("No backend bound", body)
        self.assertNotIn("Permission required", body)
        self.assertNotIn('placeholder="Pick an assistant on the left first."', body)
        self.assertNotIn(
            'data-rmc-ai-run\n                      disabled',
            body.replace(" ", ""),
        )

    def test_manager_ai_center_exposes_csrf_meta_for_ajax(self):
        u = User.objects.create_user(
            username=f"mgr_csrf_{uuid.uuid4().hex[:8]}",
            password="x" * 8,
            is_staff=True,
            is_superuser=True,
        )
        c = Client(HTTP_HOST=_MGR_HOST)
        c.login(username=u.username, password="x" * 8)
        path = reverse("siteconfig:ai_center", urlconf="config.manager_urls")
        resp = c.get(path)
        self.assertEqual(resp.status_code, 200)
        self.assertIn('meta name="csrf-token"', resp.content.decode("utf-8", errors="replace"))

    @patch("apps.portal.views_ai_gateway.get_embedding_for_text", return_value=None)
    @patch("apps.portal.views_ai_gateway.AIMemoryService.search_similar", return_value=[])
    @patch("services.ai_gateway._call_ollama", return_value=(None, {"error": "unavailable"}))
    def test_manager_superadmin_can_post_guided_assistant(
        self, _mock_ollama, _mock_search, _mock_emb
    ):
        u = User.objects.create_user(
            username=f"mgr_post_{uuid.uuid4().hex[:8]}",
            password="x" * 8,
            is_staff=False,
            is_superuser=False,
            role=User.Role.SUPERADMIN,
        )
        c = Client(HTTP_HOST=_MGR_HOST)
        c.login(username=u.username, password="x" * 8)
        url = reverse("api:ai-interop-assistant", urlconf="config.manager_urls")
        resp = c.post(
            url,
            data=json.dumps({"query": "Where is district interop configured?"}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200, resp.content[:500])
        payload = resp.json()
        self.assertTrue(payload.get("success"), payload)
        summary = (payload.get("guided") or {}).get("summary") or ""
        self.assertGreater(len(summary), 20, summary)
