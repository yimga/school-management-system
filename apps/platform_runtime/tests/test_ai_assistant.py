"""North Star SLICE 11 — AI assistant drafts, tenant isolation, audit, no auto-actions."""

from __future__ import annotations

import json
import os
import uuid
from pathlib import Path
from unittest.mock import patch

from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django_otp.plugins.otp_totp.models import TOTPDevice

from apps.accounts.models import Permission as FeaturePermission, User
from apps.people.models import StudentProfile
from apps.platform_runtime.ai_assistant_service import (
    generate_parent_message,
    log_northstar_ai_audit,
)
from apps.platform_runtime.models import AIActionAuditLog
from apps.schools.models import School, SchoolMembership

_HOST = "ns11ai.runmycampus.com"


@override_settings(
    ALLOWED_HOSTS=[
        "testserver",
        "127.0.0.1",
        "localhost",
        _HOST,
    ]
)
class NorthStarAiAssistantTests(TestCase):
    databases = {"default"}

    @classmethod
    def setUpTestData(cls):
        cls.perm_settings, _ = FeaturePermission.objects.get_or_create(
            code="settings.manage",
            defaults={"name": "Manage settings"},
        )
        cls.school_a = School.objects.create(
            name="AI School A",
            slug="ns11a",
            subdomain="ns11ai",
            is_active=True,
        )
        cls.school_b = School.objects.create(
            name="AI School B",
            slug="ns11b",
            subdomain="ns11b",
            is_active=True,
        )
        cls.student_a = StudentProfile.objects.create(
            school=cls.school_a,
            first_name="Ada",
            last_name="TenantA",
            student_code="A-001",
            is_active=True,
        )
        cls.student_b = StudentProfile.objects.create(
            school=cls.school_b,
            first_name="Bob",
            last_name="SECRETOTHER999",
            student_code="B-LEAK",
            is_active=True,
        )

    def setUp(self):
        self.client = Client(HTTP_HOST=_HOST)

    def _manage_user(self, school=None):
        school = school or self.school_a
        u = User.objects.create_user(
            username=f"ai_op_{uuid.uuid4().hex[:10]}",
            password="x" * 8,
            role=User.Role.ADMIN,
            is_staff=True,
        )
        u.feature_permissions.add(self.perm_settings)
        SchoolMembership.objects.get_or_create(
            user=u,
            school=school,
            defaults={"role": User.Role.ADMIN, "is_primary": True},
        )
        TOTPDevice.objects.create(user=u, name="test-device", confirmed=True)
        return u

    def _force_login_verified(self, user):
        self.client.force_login(user)
        session = self.client.session
        session["mfa_verified"] = True
        session.save()

    def test_ai_disabled_returns_safe_fallback_text(self):
        prev = os.environ.pop("RUNMYCAMPUS_AI_ENABLED", None)
        try:
            u = self._manage_user()
            out = generate_parent_message(
                self.student_a,
                {"topic": "grades"},
                school=self.school_a,
                user=u,
            )
            self.assertIn("disabled", (out.draft_text or "").lower())
            self.assertTrue(out.requires_approval)
        finally:
            if prev is not None:
                os.environ["RUNMYCAMPUS_AI_ENABLED"] = prev

    @patch("services.ai_gateway.invoke")
    def test_ai_enabled_invokes_gateway_and_returns_mock_draft(self, mock_invoke):
        mock_invoke.return_value = ("Mock parent draft line.", {"provider": "test"})
        prev = os.environ.get("RUNMYCAMPUS_AI_ENABLED")
        os.environ["RUNMYCAMPUS_AI_ENABLED"] = "1"
        try:
            u = self._manage_user()
            out = generate_parent_message(
                self.student_a,
                {"topic": "attendance"},
                school=self.school_a,
                user=u,
            )
            self.assertEqual(out.draft_text, "Mock parent draft line.")
            mock_invoke.assert_called()
        finally:
            if prev is None:
                os.environ.pop("RUNMYCAMPUS_AI_ENABLED", None)
            else:
                os.environ["RUNMYCAMPUS_AI_ENABLED"] = prev

    @patch("services.ai_gateway.invoke")
    def test_no_external_gateway_call_when_northstar_ai_disabled(self, mock_invoke):
        prev = os.environ.pop("RUNMYCAMPUS_AI_ENABLED", None)
        try:
            u = self._manage_user()
            generate_parent_message(
                self.student_a,
                {},
                school=self.school_a,
                user=u,
            )
            mock_invoke.assert_not_called()
        finally:
            if prev is not None:
                os.environ["RUNMYCAMPUS_AI_ENABLED"] = prev

    def test_api_respects_tenant_student_filter_no_cross_leak(self):
        prev_ai = os.environ.pop("RUNMYCAMPUS_AI_ENABLED", None)
        try:
            u = self._manage_user(self.school_a)
            self._force_login_verified(u)
            url = reverse("siteconfig:northstar_ai_draft", urlconf="config.tenant_urls")
            resp = self.client.post(
                url,
                data=json.dumps(
                    {
                        "kind": "parent_message",
                        "student_id": str(self.student_b.pk),
                        "context": {"topic": "update"},
                    }
                ),
                content_type="application/json",
            )
            self.assertEqual(resp.status_code, 200)
            body = resp.json()
            self.assertTrue(body.get("ok"))
            self.assertTrue(body.get("requires_approval"))
            self.assertNotIn("SECRETOTHER999", body.get("draft_text", ""))
            self.assertNotIn("B-LEAK", body.get("draft_text", ""))
        finally:
            if prev_ai is not None:
                os.environ["RUNMYCAMPUS_AI_ENABLED"] = prev_ai

    def test_api_requires_approval_flag_true(self):
        u = self._manage_user()
        self._force_login_verified(u)
        url = reverse("siteconfig:northstar_ai_draft", urlconf="config.tenant_urls")
        resp = self.client.post(
            url,
            data=json.dumps({"kind": "next_actions", "context": {}}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json().get("requires_approval"))

    def test_audit_log_created_for_ai_usage(self):
        before = AIActionAuditLog.objects.count()
        log_northstar_ai_audit(
            action_type="unit_parent_message",
            school=self.school_a,
            user=self._manage_user(),
            outcome="disabled",
            meta={"provider": "disabled", "task_type": None},
            draft_char_count=12,
        )
        self.assertEqual(AIActionAuditLog.objects.count(), before + 1)
        row = AIActionAuditLog.objects.order_by("-created_at").first()
        self.assertEqual(row.action_type, "unit_parent_message")
        self.assertEqual(row.payload.get("prompt_type"), "unit_parent_message")
        self.assertEqual(row.payload.get("draft_char_count"), 12)
        self.assertNotIn("draft_text", row.payload)

    def test_operator_templates_wire_ai_assistant_strip(self):
        """UI integration: hub and bulk letters include the North Star AI partial (static check)."""
        repo = Path(__file__).resolve().parents[3]
        for rel in (
            "templates/siteconfig/scheduled_reports_delivery_hub.html",
            "templates/siteconfig/bulk_letters.html",
        ):
            text = (repo / rel).read_text(encoding="utf-8")
            self.assertIn("north_star_ai_assistant_strip.html", text)
        partial = (
            repo / "templates/siteconfig/partials/north_star_ai_assistant_strip.html"
        ).read_text(encoding="utf-8")
        self.assertIn("data-rmc-ai-assistant", partial)
