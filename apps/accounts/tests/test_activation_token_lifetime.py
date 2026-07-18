"""Owner ACTIVATION links must outlive the short password-RESET window.

Reset tokens and activation/onboarding tokens both reuse Django's
``PasswordResetTokenGenerator``, which reads the single global
``settings.PASSWORD_RESET_TIMEOUT``. When that was tightened to 1h for reset
security, every activation link (welcome-email set-password, legacy-hash setup)
would have expired in 1h too — locking out exactly the operator-provisioned
owners the welcome email routes to account setup. ``ActivationTokenGenerator``
decouples them: the same token format, an independent days-long window.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from unittest import mock

from django.contrib.auth.tokens import default_token_generator
from django.test import TestCase, override_settings
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from apps.accounts.models import User
from apps.accounts.onboarding_tokens import activation_token_generator
from apps.accounts.views_legacy_setup import LegacySetupView
from apps.accounts.views_owner_onboarding import (
    OwnerOnboardingAccountView,
    _user_from_onboarding_token,
)


class ActivationTokenLifetimeTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="act_owner",
            email="act_owner@example.com",
            password="OwnerChosen!234",
        )

    def _uidb64(self):
        return urlsafe_base64_encode(force_bytes(self.user.pk))

    def test_fresh_token_valid_for_both_generators(self):
        token = activation_token_generator.make_token(self.user)
        self.assertTrue(activation_token_generator.check_token(self.user, token))
        self.assertTrue(default_token_generator.check_token(self.user, token))

    @override_settings(PASSWORD_RESET_TIMEOUT=3600, OWNER_ONBOARDING_TOKEN_DAYS=7)
    def test_activation_token_outlives_the_reset_window(self):
        token = activation_token_generator.make_token(self.user)
        later = datetime.now() + timedelta(hours=3)  # past 1h reset, within 7d
        with mock.patch.object(default_token_generator, "_now", return_value=later):
            self.assertFalse(
                default_token_generator.check_token(self.user, token),
                "reset generator should reject a 3h-old token under a 1h window",
            )
        with mock.patch.object(activation_token_generator, "_now", return_value=later):
            self.assertTrue(
                activation_token_generator.check_token(self.user, token),
                "activation link must still work 3h after it was emailed",
            )

    @override_settings(OWNER_ONBOARDING_TOKEN_DAYS=7)
    def test_activation_token_expires_after_its_own_window(self):
        token = activation_token_generator.make_token(self.user)
        way_later = datetime.now() + timedelta(days=8)
        with mock.patch.object(activation_token_generator, "_now", return_value=way_later):
            self.assertFalse(activation_token_generator.check_token(self.user, token))

    def test_check_sites_are_wired_to_the_activation_generator(self):
        """Wiring regression: the view + the token-poll validator must use the
        activation generator, not default_token_generator (1h)."""
        self.assertIs(
            OwnerOnboardingAccountView.token_generator, activation_token_generator
        )
        self.assertIs(LegacySetupView.token_generator, activation_token_generator)

        token = activation_token_generator.make_token(self.user)
        later = datetime.now() + timedelta(hours=3)
        with override_settings(PASSWORD_RESET_TIMEOUT=3600), mock.patch.object(
            activation_token_generator, "_now", return_value=later
        ):
            self.assertIsNotNone(
                _user_from_onboarding_token(self._uidb64(), token),
                "the onboarding token poll rejected a 3h-old activation token",
            )
