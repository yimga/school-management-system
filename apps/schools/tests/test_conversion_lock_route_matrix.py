"""
Route-family coverage for strict conversion lock (CONVERSION_LOCK_STRICT).

Proves allowlist tightening: no blanket /authentication/, blocked dashboards, granular finance/reports.
Unlock uses persisted school.settings via record_conversion_first_action only.
"""

from __future__ import annotations

import os
import uuid
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import Client, SimpleTestCase, TestCase, override_settings

from apps.accounts.models import User
from apps.schools.models import School, SchoolMembership

UserModel = get_user_model()


@patch.dict(
    os.environ,
    {"MULTI_TENANT_BASE_DOMAIN": "example.com"},
    clear=False,
)
@override_settings(
    ALLOWED_HOSTS=["*"],
    SECURE_SSL_REDIRECT=False,
    DEBUG=True,
    ROOT_URLCONF="config.tenant_urls",
    MULTI_TENANT_BASE_DOMAIN="example.com",
    CONVERSION_LOCK_STRICT=True,
    CONVERSION_LOCK_ALL_SCHOOLS=True,
    CONVERSION_LOCK_USE_NARROW_WORKFLOW_PATHS=True,
)
class ConversionLockRouteMatrixHttpTests(TestCase):
    """Tenant HTTP integration: locked surface redirects to activation."""

    def setUp(self):
        self.client = Client(enforce_csrf_checks=False)
        uid = uuid.uuid4().hex[:10]
        self.host = f"matrix-{uid}.example.com"
        self.school = School.objects.create(
            name=f"Matrix School {uid}",
            slug=f"matrix-{uid}",
            subdomain=f"matrix-{uid}",
            is_active=True,
            settings={},
        )

    def _login_admin(self, username: str = "matrixadm"):
        user = UserModel.objects.create_user(
            username=username,
            email=f"{username}@example.edu",
            password="Test1234!ab",
            role=User.Role.ADMIN,
            is_staff=True,
            is_superuser=True,
        )
        SchoolMembership.objects.get_or_create(
            user=user,
            school=self.school,
            defaults={"role": User.Role.ADMIN, "is_primary": True},
        )
        self.client.login(username=username, password="Test1234!ab")
        return user

    def _assert_activation_redirect(self, response):
        self.assertEqual(response.status_code, 302)
        self.assertIn("/activation/first-action/", response["Location"])

    def _assert_not_activation_redirect(self, response):
        if response.status_code == 302:
            loc = response.get("Location", "")
            self.assertNotIn(
                "/activation/first-action/",
                loc,
                msg=f"unexpected conversion lock redirect: {loc}",
            )

    def test_blocked_backend_rbac_profile_messages(self):
        self._login_admin()
        for path in (
            "/authentication/backend/",
            "/authentication/rbac/",
            "/authentication/profile/",
            "/authentication/messages/",
            "/authentication/backend/ops/",
        ):
            with self.subTest(path=path):
                r = self.client.get(path, HTTP_HOST=self.host, follow=False)
                self._assert_activation_redirect(r)

    def test_blocked_dashboards_and_hubs(self):
        self._login_admin()
        for path in (
            "/portal/teacher/",
            "/portal/parent/",
            "/finance/",
            "/marketplace/app/1/purchase-intent/",
            "/settings/app-catalog/",
            "/siteconfig/",
            "/analytics/",
            "/communication/",
            "/api/v1/",
            "/settings/installed-apps/",
            "/api/internal/metadata/",
        ):
            with self.subTest(path=path):
                r = self.client.get(path, HTTP_HOST=self.host, follow=False)
                self._assert_activation_redirect(r)

    def test_allowlisted_activation_demo_evals_attendance(self):
        self._login_admin()
        for path in (
            "/activation/first-action/",
            "/demo/flow/attendance/",
            "/portal/teacher/attendance/",
            "/evals/teacher/marks/entry/",
        ):
            with self.subTest(path=path):
                r = self.client.get(path, HTTP_HOST=self.host, follow=False)
                self.assertIn(r.status_code, (200, 302, 403))
                self._assert_not_activation_redirect(r)

    def test_finance_root_blocked_payments_prefix_not_activation_redirect(self):
        self._login_admin()
        r_dash = self.client.get("/finance/", HTTP_HOST=self.host, follow=False)
        self._assert_activation_redirect(r_dash)
        r_pay = self.client.get("/finance/payments/", HTTP_HOST=self.host, follow=False)
        self._assert_not_activation_redirect(r_pay)
        self.assertIn(r_pay.status_code, (200, 302, 403, 404))

    def test_reports_root_blocked_publish_prefix_not_activation_redirect(self):
        self._login_admin()
        r_root = self.client.get("/reports/", HTTP_HOST=self.host, follow=False)
        self._assert_activation_redirect(r_root)
        r_pub = self.client.get("/reports/publish/", HTTP_HOST=self.host, follow=False)
        self._assert_not_activation_redirect(r_pub)
        self.assertIn(r_pub.status_code, (200, 302, 403, 404))

    def test_siteconfig_reports_legacy_allowed_siteconfig_home_blocked(self):
        self._login_admin()
        r_hub = self.client.get("/siteconfig/", HTTP_HOST=self.host, follow=False)
        self._assert_activation_redirect(r_hub)
        r_rep = self.client.get("/siteconfig/reports/", HTTP_HOST=self.host, follow=False)
        self._assert_not_activation_redirect(r_rep)
        self.assertIn(r_rep.status_code, (200, 302, 403, 404))

    def test_api_health_allowlisted_internal_click_tracking_blocked(self):
        self._login_admin()
        rh = self.client.get("/api/health/", HTTP_HOST=self.host, follow=False)
        self._assert_not_activation_redirect(rh)
        rc = self.client.post(
            "/api/internal/click-tracking/",
            HTTP_HOST=self.host,
            data="{}",
            content_type="application/json",
            follow=False,
        )
        self._assert_activation_redirect(rc)

    def test_unlock_restores_backend_after_record_conversion_first_action(self):
        self._login_admin()
        from apps.schools.conversion_lock_state import record_conversion_first_action

        u = UserModel.objects.get(username="matrixadm")
        r0 = self.client.get("/authentication/backend/", HTTP_HOST=self.host, follow=False)
        self._assert_activation_redirect(r0)
        record_conversion_first_action(self.school, source="route_matrix", user=u)
        r1 = self.client.get("/authentication/backend/", HTTP_HOST=self.host, follow=False)
        self.assertEqual(r1.status_code, 200, msg=r1.get("Location"))

    def test_unlock_via_sources_uses_persisted_state_only(self):
        """Signals use the same API; sources are audit metadata — unlock is state-driven."""
        self._login_admin()
        from apps.schools.conversion_lock_state import record_conversion_first_action

        u = UserModel.objects.get(username="matrixadm")
        for src in (
            "attendance_saved",
            "marks_saved",
            "report_generated",
            "payment_recorded",
        ):
            uid = uuid.uuid4().hex[:10]
            school = School.objects.create(
                name=f"S-{src}",
                slug=f"s-{uid}",
                subdomain=f"x{uid}",
                is_active=True,
                settings={},
            )
            SchoolMembership.objects.get_or_create(
                user=u,
                school=school,
                defaults={"role": User.Role.ADMIN, "is_primary": True},
            )
            self.client.login(username="matrixadm", password="Test1234!ab")
            record_conversion_first_action(school, source=src, user=u)
            r = self.client.get(
                "/authentication/backend/",
                HTTP_HOST=f"{school.subdomain}.example.com",
                follow=False,
            )
            self.assertEqual(r.status_code, 200, msg=src)


@override_settings(
    CONVERSION_LOCK_STRICT=True,
    CONVERSION_LOCK_USE_NARROW_WORKFLOW_PATHS=True,
)
class ConversionLockAllowlistUnitTests(SimpleTestCase):
    """Pure allowlist rules (no DB)."""

    def test_strict_auth_narrow_no_profile_no_backend(self):
        from apps.schools.conversion_lock_paths import path_matches_conversion_allowlist

        self.assertFalse(
            path_matches_conversion_allowlist("/authentication/profile/", ())
        )
        self.assertFalse(path_matches_conversion_allowlist("/authentication/backend/", ()))
        self.assertTrue(path_matches_conversion_allowlist("/authentication/login/", ()))
        self.assertTrue(path_matches_conversion_allowlist("/authentication/mfa/verify/", ()))

    def test_strict_finance_root_not_allowlisted(self):
        from apps.schools.conversion_lock_paths import path_matches_conversion_allowlist

        self.assertFalse(path_matches_conversion_allowlist("/finance/", ()))
        self.assertTrue(path_matches_conversion_allowlist("/finance/payments/", ()))

    def test_strict_reports_root_not_allowlisted_publish_yes(self):
        from apps.schools.conversion_lock_paths import path_matches_conversion_allowlist

        self.assertFalse(path_matches_conversion_allowlist("/reports/", ()))
        self.assertTrue(path_matches_conversion_allowlist("/reports/publish/", ()))

    def test_strict_safe_allowlist_login_logout_mfa_activation_assets_health(self):
        """Prompt-safe surfaces: auth session paths + activation + static/media + health."""
        from apps.schools.conversion_lock_paths import path_matches_conversion_allowlist

        for path in (
            "/authentication/login/",
            "/authentication/logout/",
            "/authentication/mfa/verify/",
            "/activation/first-action/",
            "/activation/complete/",
            "/static/admin/css/base.css",
            "/media/uploads/x.pdf",
            "/health",
            "/api/health/",
        ):
            with self.subTest(path=path):
                self.assertTrue(
                    path_matches_conversion_allowlist(path, ()),
                    msg=path,
                )
