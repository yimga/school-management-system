"""
Live HTTP integration for AI health + guided assistant — no Ollama mocks.

Requires running Ollama and RMC_AI_REQUIRE_LIVE=1 in CI; skipped locally when down.
"""

from __future__ import annotations

import json
import os
import unittest
import uuid

from django.test import Client, TestCase, override_settings, tag
from django.urls import reverse
from django_otp.plugins.otp_totp.models import TOTPDevice

from apps.accounts.models import Permission, User
from apps.people.models import TeacherProfile
from apps.siteconfig.models import Plan
from apps.schools.models import School

_T_HOST = "ailive.runmycampus.com"


def _ollama_reachable() -> bool:
    from apps.portal.ai_provider import probe_ai_provider_reachable

    return bool(probe_ai_provider_reachable().get("reachable"))


def _live_guard() -> None:
    if _ollama_reachable():
        return
    if os.getenv("RMC_AI_REQUIRE_LIVE", "").strip().lower() in ("1", "true", "yes"):
        raise AssertionError("Live Ollama required but unreachable")
    raise unittest.SkipTest("Ollama not reachable")


@tag("ai_live_ollama")
@override_settings(ALLOWED_HOSTS=["testserver", "127.0.0.1", "localhost", _T_HOST])
@unittest.skipUnless(
    os.getenv("RMC_AI_REQUIRE_LIVE", "").strip().lower() in ("1", "true", "yes")
    or _ollama_reachable(),
    "live Ollama only",
)
class AILiveHttpIntegrationTests(TestCase):
    databases = {"default"}

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        _live_guard()

    @classmethod
    def setUpTestData(cls):
        cls.plan = Plan.objects.create(name="Free", slug="basic", is_active=True)
        cls.school = School.objects.create(
            name="AI Live School",
            slug="ailive",
            subdomain="ailive",
            is_active=True,
            plan=cls.plan,
        )
        cls.perm_settings, _ = Permission.objects.get_or_create(
            code="settings.manage",
            defaults={"name": "Manage settings"},
        )

    def _staff_client(self):
        u = User.objects.create_user(
            username=f"ai_live_{uuid.uuid4().hex[:8]}",
            password="x" * 8,
            role=User.Role.ADMIN,
            is_staff=True,
        )
        u.feature_permissions.add(self.perm_settings)
        TeacherProfile.objects.create(
            user=u, school=self.school, staff_id=f"AL{uuid.uuid4().hex[:4].upper()}"
        )
        TOTPDevice.objects.update_or_create(
            user=u, name="test-mfa", defaults={"confirmed": True}
        )
        c = Client(HTTP_HOST=_T_HOST)
        c.login(username=u.username, password="x" * 8)
        session = c.session
        session["mfa_verified"] = True
        session.save()
        return c

    def test_ai_health_reports_reachable(self):
        c = self._staff_client()
        url = reverse("api:ai_health", urlconf="config.tenant_urls")
        resp = c.get(url)
        self.assertEqual(resp.status_code, 200)
        payload = resp.json()
        self.assertTrue(payload.get("success"))
        self.assertTrue(payload.get("reachable"), payload)
        self.assertEqual(payload.get("provider"), "ollama")

    def test_interop_assistant_post_live_ollama_tier(self):
        c = self._staff_client()
        url = reverse("api:ai-interop-assistant", urlconf="config.tenant_urls")
        resp = c.post(
            url,
            data=json.dumps({"query": "Where is district interop configured?"}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        payload = resp.json()
        self.assertTrue(payload.get("success"), payload)
        guided = payload.get("guided") or {}
        self.assertGreater(len((guided.get("summary") or "")), 20, payload)
        meta = payload.get("meta") or {}
        tier = meta.get("tier") or meta.get("provider")
        self.assertEqual(tier, "ollama", meta)
        self.assertFalse(meta.get("fallback"), meta)
