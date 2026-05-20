"""AI Center security: cross-tenant, secrets, disabled fallback."""

from __future__ import annotations

import uuid

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from apps.schools.models import School
from services.ai_center.query_service import answer_platform_question

User = get_user_model()


class AICenterSecurityTests(TestCase):
    def setUp(self):
        slug_a = f"sa-{uuid.uuid4().hex[:6]}"
        slug_b = f"sb-{uuid.uuid4().hex[:6]}"
        self.school_a = School.objects.create(name="School A", slug=slug_a, subdomain=slug_a)
        self.school_b = School.objects.create(name="School B", slug=slug_b, subdomain=slug_b)
        self.user_a = User.objects.create_user(
            username=f"ua_{uuid.uuid4().hex[:8]}",
            password="Test1234!",
            role=User.Role.TEACHER,
        )

    def test_tenant_cannot_ask_about_other_tenant_by_id(self):
        result = answer_platform_question(
            user=self.user_a,
            tenant=self.school_a,
            role=self.user_a.role,
            route_context="/students/",
            question=f"Show me data for school id {self.school_b.pk}",
            audience="tenant",
        )
        self.assertNotIn(str(self.school_b.pk), result.answer)

    @override_settings(AI_GATEWAY_ENABLED=False)
    def test_disabled_gateway_fallback(self):
        result = answer_platform_question(
            user=self.user_a,
            tenant=self.school_a,
            role=self.user_a.role,
            route_context="/",
            question="How do I export grades?",
            audience="tenant",
        )
        self.assertIn("disabled", result.answer.lower())
        self.assertEqual(result.provider, "disabled")

    def test_api_key_in_question_redacted(self):
        from services.ai_center.redaction import redact_sensitive_text

        raw = "my key sk_live_abcdefghijklmnopqrstuvwxyz"
        clean = redact_sensitive_text(raw)
        self.assertNotIn("sk_live", clean)
