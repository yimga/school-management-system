"""The owner-onboarding launchpad surfaces MFA setup until the owner enrolls.

The provisioned owner has role ADMIN, which ``BASELINE_REQUIRED_ROLES`` makes
MFA-required (enforced by ``RequireMFAMiddleware`` at first dashboard access).
The launchpad CTA turns that required step into a visible part of first-run
setup instead of a surprise redirect; it must reflect real enrollment state so
it hides once a *confirmed* device exists (an unconfirmed, half-set-up device
must NOT count as protected).
"""

from __future__ import annotations

from django.test import RequestFactory, TestCase
from django.urls import reverse

from apps.accounts.models import User
from apps.accounts.views_owner_onboarding import (
    _owner_mfa_enrolled,
    _post_onboarding_dashboard_href,
)
from apps.schools.models import School


class OwnerMfaEnrolledTests(TestCase):
    def _user(self, name):
        return User.objects.create_user(name, f"{name}@example.com", "pw")

    def test_no_device_means_not_enrolled(self):
        self.assertFalse(_owner_mfa_enrolled(self._user("mfa_owner")))

    def test_confirmed_totp_device_means_enrolled(self):
        from django_otp.plugins.otp_totp.models import TOTPDevice

        user = self._user("mfa_owner2")
        TOTPDevice.objects.create(user=user, name="phone", confirmed=True)
        self.assertTrue(_owner_mfa_enrolled(user))

    def test_unconfirmed_device_does_not_count_as_protected(self):
        from django_otp.plugins.otp_totp.models import TOTPDevice

        user = self._user("mfa_owner3")
        TOTPDevice.objects.create(user=user, name="pending", confirmed=False)
        self.assertFalse(_owner_mfa_enrolled(user))


class OwnerDashboardHrefMfaGateTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.school = School.objects.create(
            name="MFA Gate School",
            slug="mfa-gate-school",
            subdomain="mfa-gate-school",
            is_active=True,
        )

    def test_unenrolled_owner_dashboard_cta_routes_through_mfa_setup(self):
        user = User.objects.create_user("mfa_gate", "mfa_gate@example.com", "pw")
        request = self.factory.get("/authentication/onboarding/done/")
        request.user = user
        href = _post_onboarding_dashboard_href(request, self.school)
        self.assertIn(reverse("accounts:owner_onboarding_mfa"), href)
        self.assertNotIn("mfa_setup", href)

    def test_enrolled_owner_gets_direct_dashboard(self):
        from django_otp.plugins.otp_totp.models import TOTPDevice

        user = User.objects.create_user("mfa_ok", "mfa_ok@example.com", "pw")
        TOTPDevice.objects.create(user=user, name="phone", confirmed=True)
        request = self.factory.get("/authentication/onboarding/done/")
        request.user = user
        href = _post_onboarding_dashboard_href(request, self.school)
        self.assertNotIn("owner_onboarding_mfa", href)
        self.assertNotIn("mfa_setup", href)
