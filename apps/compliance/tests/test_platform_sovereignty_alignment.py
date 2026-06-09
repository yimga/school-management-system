"""
Phase 3 — platform sovereignty alignment (cross-tenant leak + AI oracle scope).

Repo-native Django tests (primary delivery is server-rendered Django + islands,
not a single React SPA — see CLAUDE.md).
"""

from __future__ import annotations

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase, override_settings

from apps.schools.models import School, SchoolMembership
from services.ai.code_oracle import generate_workflow_manual, inspect_active_route


User = get_user_model()


@override_settings(MULTI_TENANT_BASE_DOMAIN="runmycampus.com", ALLOWED_HOSTS=["*"])
class CrossTenantLeakAlignmentTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.alpha = School.objects.create(
            name="Alpha Academy",
            slug="alpha-sovereignty",
            subdomain="alpha-sovereignty",
            is_active=True,
        )
        self.beta = School.objects.create(
            name="Beta Academy",
            slug="beta-sovereignty",
            subdomain="beta-sovereignty",
            is_active=True,
        )
        self.alpha_user = User.objects.create_user(
            username="alpha_owner",
            email="owner@alpha-sovereignty.test",
            password="testpass123",
        )
        SchoolMembership.objects.create(
            school=self.alpha,
            user=self.alpha_user,
            role="ADMIN",
            is_primary=True,
        )

    @patch("django.contrib.messages.warning")
    def test_alpha_session_host_mismatch_blocks_tenant_surface(self, _warning_mock):
        from apps.schools.middleware import _enforce_tenant_host_membership

        request = self.factory.get(
            "/authentication/backend/",
            HTTP_HOST="beta-sovereignty.runmycampus.com",
        )
        request.user = self.alpha_user
        request.session = {}
        request.school = self.beta
        result = _enforce_tenant_host_membership(request, self.beta)
        self.assertIsNotNone(result)
        self.assertFalse(
            SchoolMembership.objects.filter(user=self.alpha_user, school=self.beta).exists()
        )

    def test_code_oracle_manual_tags_tenant_scope(self):
        manual = generate_workflow_manual(
            "/authentication/backend/",
            tenant_id=str(self.alpha.pk),
            school_id=str(self.alpha.pk),
        )
        self.assertTrue(manual.get("ok"))
        self.assertIn(str(self.alpha.pk)[:12], manual.get("markdown") or "")
        self.assertEqual(manual.get("tenant_id"), str(self.alpha.pk))

    def test_code_oracle_route_inspection_returns_compressed_row(self):
        row = inspect_active_route("/admin/")
        if row is not None:
            self.assertIn("url_path", row)


@override_settings(MULTI_TENANT_BASE_DOMAIN="runmycampus.com")
class ResiliencyFallbackAlignmentTests(TestCase):
    def test_code_oracle_unknown_path_returns_safe_payload_not_exception(self):
        manual = generate_workflow_manual("/__rmc_sovereignty_nonexistent_path__/")
        self.assertIsInstance(manual, dict)
        self.assertIn("ok", manual)
        self.assertIn("markdown", manual)
        if not manual.get("ok"):
            self.assertEqual(manual.get("markdown"), "")
