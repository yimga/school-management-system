"""
Route-family coverage for strict conversion lock (CONVERSION_LOCK_STRICT).

Proves allowlist tightening: no blanket /authentication/, blocked dashboards, granular finance/reports.
Unlock uses persisted school.settings via record_conversion_first_action only.
"""

from __future__ import annotations

import os
import uuid
from unittest.mock import patch
from urllib.parse import urlsplit

from django.contrib.auth import get_user_model
from django.test import Client, SimpleTestCase, TestCase, override_settings
from django_otp.plugins.otp_totp.models import TOTPDevice

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
        # HTTP_ACCEPT="text/html" marks every request a top-level document
        # navigation (is_document_navigation), which is what the conversion-lock
        # gate keys on — a bare test-client GET sends no Accept header, so the
        # gate correctly treats it as an XHR/subresource and never redirects
        # (the "empty-void" storm fix). A real browser page load always sends it.
        self.client = Client(enforce_csrf_checks=False, HTTP_ACCEPT="text/html")
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
        # These admins are is_superuser=True, so principal_requires_strict_mfa()
        # hard-walls them to /authentication/mfa/setup/ ahead of the conversion
        # lock (security gate outranks the onboarding gate). Enroll + verify MFA
        # so the request reaches the conversion-lock gate the tests exercise —
        # exactly the state of a real admin who has completed MFA enrollment.
        self._mark_mfa_verified(user)
        return user

    def _mark_mfa_verified(self, user):
        TOTPDevice.objects.get_or_create(
            user=user,
            name="test-device",
            defaults={"confirmed": True},
        )
        session = self.client.session
        session["mfa_verified"] = True
        session.save()

    def _assert_activation_redirect(self, response):
        self.assertEqual(response.status_code, 302)
        self.assertIn("/activation/first-action/", response["Location"])

    def _assert_not_activation_redirect(self, response):
        if response.status_code == 302:
            loc = response.get("Location", "")
            self.assertNotEqual(
                urlsplit(loc).path,
                "/activation/first-action/",
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
        self._mark_mfa_verified(u)
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
            self._mark_mfa_verified(u)
            r = self.client.get(
                "/authentication/backend/",
                HTTP_HOST=f"{school.subdomain}.example.com",
                follow=False,
            )
            self.assertEqual(r.status_code, 200, msg=src)


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
class FreshOwnerOnboardingNoRedirectLoopTests(TestCase):
    """General seal against the ERR_TOO_MANY_REDIRECTS class for ALL future
    tenants. Simulates a brand-new ADMIN owner — authenticated, NOT activated
    (no first_action), and with NO confirmed MFA device — exactly the state of
    a freshly provisioned tenant. Follows redirects from every entry URL and
    fails if the chain ever revisits a path (a loop) or never terminates. This
    catches any gate (conversion lock, MFA, activation, a future one) that
    bounces an owner in a cycle, regardless of which allowlist drifts.
    """

    def setUp(self):
        self.client = Client(enforce_csrf_checks=False)
        uid = uuid.uuid4().hex[:10]
        self.host = f"loop-{uid}.example.com"
        self.school = School.objects.create(
            name=f"Loop School {uid}",
            slug=f"loop-{uid}",
            subdomain=f"loop-{uid}",
            is_active=True,
            settings={},  # no first_action_completed → conversion lock active
        )
        # Brand-new ADMIN owner with NO MFA device and NO mfa_verified session
        # → RequireMFAMiddleware is live. This is the loop-prone state.
        self.user = UserModel.objects.create_user(
            username=f"owner{uid}",
            email=f"owner{uid}@example.edu",
            password="Test1234!ab",
            role=User.Role.ADMIN,
            is_staff=True,
        )
        SchoolMembership.objects.get_or_create(
            user=self.user,
            school=self.school,
            defaults={"role": User.Role.ADMIN, "is_primary": True},
        )
        self.client.login(username=self.user.username, password="Test1234!ab")

    def _assert_terminates_without_loop(self, start_path, max_hops=15):
        chain: list[str] = []
        path = start_path
        for _ in range(max_hops):
            if path in chain:
                self.fail(
                    "redirect loop (ERR_TOO_MANY_REDIRECTS) revisiting "
                    f"{path}: chain={' -> '.join(chain)} -> {path}"
                )
            chain.append(path)
            r = self.client.get(path, HTTP_HOST=self.host, follow=False)
            if r.status_code in (301, 302, 303, 307, 308):
                loc = r.get("Location", "") or ""
                path = urlsplit(loc).path or "/"
                continue
            return r  # terminal response (200/403/404/500) — no loop
        self.fail(
            f"redirect chain did not terminate within {max_hops} hops "
            f"starting at {start_path}: {' -> '.join(chain)}"
        )

    def test_entry_urls_never_loop_for_fresh_unactivated_owner(self):
        # The exact URLs the owner reported dead on new-school + the shell root.
        for start in (
            "/",
            "/activation/first-action/",
            "/school/studio/wizards/mfa_setup/",
            "/authentication/backend/identity/invite/",
        ):
            with self.subTest(entry=start):
                self._assert_terminates_without_loop(start)


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

    # Canonical set of pages the platform's OWN gates redirect a brand-new owner
    # to (or that an owner must reach to complete first-action) while strict
    # conversion lock is active. RequireMFAMiddleware → accounts:mfa_setup
    # (/authentication/mfa/setup/, which 302s to the wizard-engine surface) and
    # accounts:mfa_verify; ConversionLockMiddleware → /activation/first-action/;
    # owner onboarding wizard + invite-claim are token-authed first-run flows.
    # If ANY of these is not allowlisted, a gate bounces it and onboarding loops.
    # Keep this list in lockstep with the gates' own exemptions.
    ONBOARDING_REACHABLE_UNDER_LOCK = (
        "/authentication/login/",
        "/authentication/logout/",
        "/authentication/mfa/setup/",
        "/authentication/mfa/verify/",
        "/authentication/mfa/passkey/register/",
        "/school/studio/wizards/mfa_setup/",
        "/school/studio/wizards/mfa_verify/",
        "/activation/first-action/",
        "/authentication/onboarding/account/",
        "/authentication/claim-invite/abc123/",
    )

    def test_all_onboarding_redirect_destinations_reachable_under_strict_lock(self):
        """Parity seal: every page the gates send a new owner to MUST be
        reachable under strict conversion lock, so no future tenant can hit an
        onboarding redirect loop. Drift here is exactly the bug class that broke
        new-school (ConversionLock omitted /school/studio/ → MFA-gate↔lock loop).
        """
        from apps.schools.conversion_lock_paths import path_matches_conversion_allowlist

        for path in self.ONBOARDING_REACHABLE_UNDER_LOCK:
            with self.subTest(must_be_reachable=path):
                self.assertTrue(
                    path_matches_conversion_allowlist(path, ()),
                    msg=(
                        f"{path} is a gate redirect destination but is NOT "
                        f"allowlisted under strict conversion lock → onboarding "
                        f"loop. Add its prefix to conversion_lock_paths.py in "
                        f"parity with the gate that redirects to it."
                    ),
                )

    def test_strict_school_studio_wizard_allowlisted_breaks_mfa_onboarding_loop(self):
        """Regression seal: the Unified Wizard Engine surface must be reachable
        under strict conversion lock.

        RequireMFAMiddleware redirects ADMIN owners to
        /school/studio/wizards/mfa_setup/ (and exempts that path). If the strict
        conversion-lock allowlist omits /school/studio/ it bounces the wizard
        page back to /activation/first-action/, where the MFA gate re-redirects
        to the wizard — an ERR_TOO_MANY_REDIRECTS loop that walls a brand-new
        owner out of onboarding. This keeps ConversionLock in parity with
        ActivationGateMiddleware._path_exempt (which already exempts it).
        """
        from apps.schools.conversion_lock_paths import path_matches_conversion_allowlist

        for path in (
            "/school/studio/wizards/mfa_setup/",
            "/school/studio/wizards/mfa_verify/",
            "/school/studio/",
        ):
            with self.subTest(allowed=path):
                self.assertTrue(
                    path_matches_conversion_allowlist(path, ()),
                    msg=f"{path} must be allowlisted to break the MFA onboarding loop",
                )
        # The fix must NOT loosen the locked backend/RBAC/profile surfaces.
        for path in (
            "/authentication/backend/identity/invite/",
            "/authentication/backend/",
            "/authentication/rbac/",
        ):
            with self.subTest(still_locked=path):
                self.assertFalse(
                    path_matches_conversion_allowlist(path, ()),
                    msg=f"{path} must stay locked under strict conversion lock",
                )
