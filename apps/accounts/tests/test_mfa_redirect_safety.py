from unittest import mock

from django.contrib.auth import get_user_model
from django.http import HttpResponse
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse

from apps.accounts.middleware import RequireMFAMiddleware
from apps.accounts.middleware_security_posture import SecurityPostureReviewMiddleware


User = get_user_model()


def _ok_response(request):
    return HttpResponse("ok")


class MfaRedirectSafetyTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="mfa-user",
            email="mfa-user@example.com",
            password="password",
        )
        self.client.force_login(self.user)

    def test_dismiss_mfa_banner_rejects_external_next(self):
        response = self.client.get(
            reverse("accounts:dismiss_mfa_banner"),
            {"next": "https://evil.example/phish"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/admin/")


class RequireMfaPostLoginRedirectBypassTests(TestCase):
    """ADMIN owners must reach redirect_view before MFA setup (signup/onboarding path)."""

    def test_redirect_bypasses_mfa_gate_when_path_is_normalized(self):
        user = User.objects.create_user(
            username="new-owner",
            email="new-owner@example.com",
            password="password",
            role="ADMIN",
        )
        factory = RequestFactory()
        request = factory.get("/authentication/redirect/")
        request.user = user
        request.session = {}
        middleware = RequireMFAMiddleware(_ok_response)
        response = middleware(request)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"ok")


class RequireMfaWizardSetupBypassTests(TestCase):
    """The Unified Wizard Engine MFA-setup surface must stay reachable.

    accounts:mfa_setup (v4.00.12+) 302-redirects to
    /school/studio/wizards/mfa_setup/. If the middleware re-gates that path,
    a no-device MFA-required owner is bounced off the very page where they
    enroll → infinite mfa/setup -> wizard -> mfa/setup loop (the new-owner
    onboarding loop). These tests lock the page open while keeping every
    other path enforced.
    """

    def setUp(self):
        self.factory = RequestFactory()
        self.user = User.objects.create_user(
            username="loop-owner",
            email="loop-owner@example.com",
            password="password",
            role="ADMIN",
            is_staff=True,
        )
        # Force MFA-required so a missing device WOULD redirect non-exempt paths.
        site = mock.Mock(require_mfa_all_staff=True, require_mfa_roles=[])
        patcher = mock.patch(
            "apps.accounts.middleware.get_effective_site_settings",
            return_value=site,
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def _run(self, path):
        request = self.factory.get(path)
        request.user = self.user
        request.session = {}
        return RequireMFAMiddleware(_ok_response)(request)

    def test_wizard_mfa_setup_is_reachable(self):
        # Regression: without the wizards/mfa_setup bypass this 302s back to
        # /authentication/mfa/setup/ and the owner can never enroll.
        response = self._run("/school/studio/wizards/mfa_setup/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"ok")

    def test_legacy_mfa_setup_is_reachable(self):
        response = self._run("/authentication/mfa/setup/")
        self.assertEqual(response.status_code, 200)

    def test_non_setup_path_still_enforced(self):
        response = self._run("/portal/")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/mfa/setup", response.url)


@override_settings(SECURITY_POSTURE_REVIEW_NAG_ENABLED=True)
class SecurityPostureMfaSetupExemptionTests(TestCase):
    """The quarterly security-posture nag must not interrupt MFA enrollment.

    RequireMFAMiddleware already exempts /school/studio/wizards/mfa_setup/
    (see RequireMfaWizardSetupBypassTests). SecurityPostureReviewMiddleware was
    never updated to match: EXEMPT_VIEW_NAMES exempts the accounts:mfa_setup
    *shim* but not the studio wizard view that actually renders enrollment, so a
    no-device owner gets bounced wizard -> security-review -> mfa/setup -> wizard
    on first login. These lock the MFA-setup surface open while keeping the nag
    firing on every other page.
    """

    def setUp(self):
        self.factory = RequestFactory()
        self.user = User.objects.create_user(
            username="posture-owner",
            email="posture-owner@example.com",
            password="password",
            role="ADMIN",
        )

    def _run(self, path, view_name):
        request = self.factory.get(path)
        request.user = self.user
        request.session = {}
        request.resolver_match = mock.Mock(view_name=view_name)
        with mock.patch(
            "apps.accounts.middleware_security_posture.is_security_posture_review_due",
            return_value=True,
        ):
            return SecurityPostureReviewMiddleware(_ok_response)(request)

    def test_mfa_setup_wizard_not_hijacked_by_posture_nag(self):
        response = self._run(
            "/school/studio/wizards/mfa_setup/", "setup_studio:tenant_wizard_step"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"ok")

    def test_normal_page_still_nagged_when_review_due(self):
        # The nag must still fire on a non-MFA page (otherwise the exemption
        # silently disabled the whole quarterly review).
        response = self._run("/portal/", "portal:home")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/security/review", response.url)
