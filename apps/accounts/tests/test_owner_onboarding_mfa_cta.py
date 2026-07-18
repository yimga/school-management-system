"""The owner-onboarding launchpad surfaces MFA setup until the owner enrolls.

The provisioned owner has role ADMIN, which ``BASELINE_REQUIRED_ROLES`` makes
MFA-required (enforced by ``RequireMFAMiddleware`` at first dashboard access).
The launchpad CTA turns that required step into a visible part of first-run
setup instead of a surprise redirect; it must reflect real enrollment state so
it hides once a *confirmed* device exists (an unconfirmed, half-set-up device
must NOT count as protected).
"""

from __future__ import annotations

from django.test import TestCase

from apps.accounts.models import User
from apps.accounts.views_owner_onboarding import _owner_mfa_enrolled


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
