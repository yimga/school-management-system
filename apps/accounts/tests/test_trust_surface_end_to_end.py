"""
Trust surface contract (Phase 8): hub deep links resolve; MFA, sessions, activity,
governance targets reachable with school context for a superuser.
"""

from __future__ import annotations

import uuid

from django.test import SimpleTestCase, TestCase
from django.urls import NoReverseMatch, reverse

from apps.accounts.models import User
from apps.schools.models import School, SchoolMembership

# Mirrors apps.accounts.views_trust_hub security_trust_hub URL map (must stay in sync).
_TRUST_HUB_DEEP_LINK_NAMES = (
    "accounts:mfa_setup",
    "accounts:sessions_page",
    "accounts:api_security_export_log",
    "accounts:api_security_activity",
    "accounts:rbac",
    "compliance:dashboard",
    "apicenter:dashboard",
    "accounts:tenant_activity_log",
    "accounts:tenant_impersonation_audit",
    "siteconfig:feature_control_panel",
    "siteconfig:feature_control_audit",
    "accounts:backend_dashboard",
)


class TrustSurfaceUrlContractTests(SimpleTestCase):
    def test_trust_hub_deep_links_resolve(self) -> None:
        for name in _TRUST_HUB_DEEP_LINK_NAMES:
            with self.subTest(url_name=name):
                try:
                    path = reverse(name)
                except NoReverseMatch as e:
                    self.fail(f"{name} must reverse: {e}")
                self.assertTrue(path.startswith("/"), name)


class TrustSurfaceHttpFlowTests(TestCase):
    """Integration: session school_id + superuser can traverse the trust spine."""

    def setUp(self) -> None:
        self.school = School.objects.create(
            name="Trust E2E School",
            slug=f"te-{uuid.uuid4().hex[:10]}",
            subdomain=f"te-{uuid.uuid4().hex[:10]}",
            is_active=True,
        )
        self.user = User.objects.create_user(
            username=f"su-{uuid.uuid4().hex[:8]}",
            email="trust-e2e@example.com",
            password="trust-e2e-pass",
            is_staff=True,
            is_superuser=True,
        )
        SchoolMembership.objects.create(
            user=self.user,
            school=self.school,
            role=User.Role.ADMIN,
            is_primary=True,
        )
        self.client.force_login(self.user)
        session = self.client.session
        session["school_id"] = str(self.school.id)
        session.save()

    def test_security_trust_hub_renders(self) -> None:
        r = self.client.get(reverse("accounts:security_trust_hub"))
        self.assertEqual(r.status_code, 200)
        body = r.content.decode("utf-8").lower()
        self.assertIn("security", body)
        self.assertIn("mfa", body)

    def test_mfa_setup_reachable(self) -> None:
        r = self.client.get(reverse("accounts:mfa_setup"))
        self.assertIn(r.status_code, (200, 302))

    def test_sessions_page_renders(self) -> None:
        r = self.client.get(reverse("accounts:sessions_page"))
        self.assertEqual(r.status_code, 200)
        body = r.content.decode("utf-8").lower()
        self.assertTrue(
            "revoke" in body or "session" in body or "device" in body,
            msg="sessions page should mention sessions or devices",
        )

    def test_api_security_activity_json(self) -> None:
        r = self.client.get(reverse("accounts:api_security_activity"))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.headers.get("Content-Type", "").split(";")[0], "application/json")

    def test_tenant_impersonation_audit_renders(self) -> None:
        r = self.client.get(reverse("accounts:tenant_impersonation_audit"))
        self.assertEqual(r.status_code, 200)

    def test_tenant_activity_log_renders(self) -> None:
        r = self.client.get(reverse("accounts:tenant_activity_log"))
        self.assertEqual(r.status_code, 200)

    def test_rbac_dashboard_renders_for_superuser(self) -> None:
        r = self.client.get(reverse("accounts:rbac"))
        self.assertEqual(r.status_code, 200)

    def test_compliance_dashboard_renders(self) -> None:
        r = self.client.get(reverse("compliance:dashboard"))
        self.assertEqual(r.status_code, 200)

    def test_apicenter_dashboard_allowed_or_feature_gated(self) -> None:
        r = self.client.get(reverse("apicenter:dashboard"))
        self.assertIn(r.status_code, (200, 403))

    def test_feature_control_panel_allowed_or_gated(self) -> None:
        r = self.client.get(reverse("siteconfig:feature_control_panel"))
        self.assertIn(r.status_code, (200, 302, 403))
