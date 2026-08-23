"""The password-reset sign-in door must issue the MFA challenge too.

``test_alt_login_paths_enforce_mfa.py`` closed the magic-link, join-code and
claim-invite doors: each now calls ``resolve_post_login_mfa_redirect`` after
``login()``. The password-reset door named in the same finding was left open.

``LegacySetupView`` (the one-time setup link the 12-month legacy-hash sunset task
emails) sets ``post_reset_login = True``, so Django's ``PasswordResetConfirmView``
calls ``auth_login`` for it -- ``resolve_post_login_mfa_redirect`` is never
reached. ``RequireMFAMiddleware`` does not cover the gap: ``resolve_mfa_enforcement``
returns ``"none"`` the moment the account has a confirmed device, and the
middleware never inspects ``session["mfa_verified"]``.

So a bursar with TOTP who is emailed a sunset link gets a fully privileged
session with no code ever requested -- second factor reduced to possession of the
mailbox, exactly as it was through the magic link.

``OwnerOnboardingAccountView`` sets the same flag and is deliberately NOT changed:
it lives under ``/authentication/onboarding/``, which ``RequireMFAMiddleware``
bypasses on purpose so a brand-new passwordless owner is not walled out of their
own setup, and the wizard offers enrollment at its end.
"""

from __future__ import annotations

import uuid

from django.contrib.auth.views import INTERNAL_RESET_SESSION_TOKEN
from django.test import TestCase
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from django_otp.plugins.otp_totp.models import TOTPDevice

from apps.accounts.models import User
from apps.accounts.onboarding_tokens import activation_token_generator
from apps.schools.models import School, SchoolMembership

NEW_PASSWORD = "Str0ng-Pass-2026!"


class LegacySetupHonoursMfaTests(TestCase):
    def setUp(self) -> None:
        tag = uuid.uuid4().hex[:10]
        self.school = School.objects.create(
            name="Sunset High",
            slug=f"sun-{tag}",
            subdomain=f"sun-{tag}",
            is_active=True,
        )
        self.host = f"{self.school.subdomain}.runmycampus.com"

    def _member(self, role):
        tag = uuid.uuid4().hex[:8]
        user = User.objects.create_user(
            username=f"{role.lower()}-{tag}",
            email=f"{role.lower()}-{tag}@example.com",
            password="old-pass-12345678",
            role=role,
        )
        user.legacy_password_hash = "$2b$12$notarealhashjustaplaceholderxx"
        user.legacy_hash_algorithm = "powerschool-pbkdf2"
        user.save(update_fields=["legacy_password_hash", "legacy_hash_algorithm"])
        SchoolMembership.objects.create(user=user, school=self.school, role=role)
        return user

    def _set_password(self, user):
        """Walk the real two-step reset-confirm flow and submit the new password."""
        url = reverse(
            "accounts:legacy_setup",
            kwargs={
                "uidb64": urlsafe_base64_encode(force_bytes(user.pk)),
                "token": activation_token_generator.make_token(user),
            },
        )
        first = self.client.get(url, HTTP_HOST=self.host)
        self.assertEqual(
            first.status_code,
            302,
            "the token step must accept the link before the password step runs",
        )
        return self.client.post(
            first["Location"],
            {"new_password1": NEW_PASSWORD, "new_password2": NEW_PASSWORD},
            HTTP_HOST=self.host,
        )

    def _assert_the_setup_actually_completed(self, user):
        """Guard: without this, a 302 to anywhere would satisfy the assertions.

        A rejected token, a form error or a moved route all produce a response
        that is not the dashboard -- only the saved password and the cleared
        legacy fields prove ``form_valid`` ran to the end.
        """
        user.refresh_from_db()
        self.assertTrue(user.check_password(NEW_PASSWORD))
        self.assertEqual(user.legacy_password_hash, "")
        self.assertEqual(user.legacy_hash_algorithm, "")

    def test_enrolled_user_is_challenged_instead_of_landing_signed_in(self):
        user = self._member(User.Role.ADMIN)
        TOTPDevice.objects.create(user=user, name="phone", confirmed=True)

        response = self._set_password(user)

        self._assert_the_setup_actually_completed(user)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/mfa/verify", response["Location"])
        # The session IS signed in -- the challenge gates a live privileged
        # session, it does not merely fail the sign-in.
        self.assertEqual(self.client.session.get("_auth_user_id"), str(user.pk))
        self.assertNotIn("mfa_verified", self.client.session)

    def test_an_unenrolled_user_still_completes_setup(self):
        """Guard: the fix must not wall an account with no device.

        A sunset-link user typically has no TOTP at all; challenging them for a
        code they cannot produce would strand every migrated account.
        """
        user = self._member(User.Role.PARENT)

        response = self._set_password(user)

        self._assert_the_setup_actually_completed(user)
        self.assertEqual(response.status_code, 302)
        self.assertNotIn("/mfa/verify", response["Location"])

    def test_the_reset_token_is_still_consumed(self):
        """The MFA hop must not leave the one-time link replayable."""
        user = self._member(User.Role.ADMIN)
        TOTPDevice.objects.create(user=user, name="phone", confirmed=True)

        self._set_password(user)

        self.assertNotIn(INTERNAL_RESET_SESSION_TOKEN, self.client.session)
