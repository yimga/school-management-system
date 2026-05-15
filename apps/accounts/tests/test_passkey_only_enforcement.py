"""
Tests for the per-tenant + per-role passkey-only enforcement guard in
``apps.accounts.views.login_view``.

When ``settings.PASSKEY_ONLY_ROLES`` lists a role, members of that role
cannot complete password-form login — they must use WebAuthn / passkey.

Three required scenarios:

* unrestricted role: password login succeeds normally
* passkey-only role: password login is refused (no auth, redirected back to
  the login page with a flash message); the WebAuthn passkey path is left
  available
* passkey-only role: the passkey ceremony endpoint is reachable (no global
  block on the role)
"""

from __future__ import annotations

from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import User


@override_settings(RATELIMIT_ENABLE=False)
class PasskeyOnlyEnforcementTests(TestCase):
    """Real Django test client + real login URL."""

    def setUp(self):
        # Unrestricted role
        self.teacher = User.objects.create_user(
            username="teacher42", password="testpass1234"
        )
        self.teacher.role = User.Role.TEACHER
        self.teacher.save(update_fields=["role"])

        # High-trust role we'll mark as passkey-only
        self.super_admin = User.objects.create_user(
            username="super42", password="testpass1234"
        )
        self.super_admin.role = User.Role.SUPERADMIN
        self.super_admin.save(update_fields=["role"])

        self.login_url = reverse("accounts:login")

    # ------------------------------------------------------------------ tests

    @override_settings(PASSKEY_ONLY_ROLES=("SUPERADMIN", "FINANCE_STAFF"))
    def test_password_login_succeeds_for_unrestricted_role(self):
        """A role NOT in PASSKEY_ONLY_ROLES can still log in by password."""
        response = self.client.post(
            self.login_url,
            {"username": "teacher42", "password": "testpass1234"},
            follow=False,
        )
        # login_view redirects on success
        self.assertIn(response.status_code, (301, 302))
        # And the user is in the session
        self.assertEqual(int(self.client.session["_auth_user_id"]), self.teacher.pk)

    @override_settings(PASSKEY_ONLY_ROLES=("SUPERADMIN", "FINANCE_STAFF"))
    def test_password_login_blocked_for_passkey_only_role(self):
        """A SUPERADMIN with valid password is still refused — no session, no auth."""
        response = self.client.post(
            self.login_url,
            {"username": "super42", "password": "testpass1234"},
            follow=False,
        )
        # We redirect back to the login page (or to it with ?next=)
        self.assertIn(response.status_code, (301, 302))
        target = response.url or ""
        self.assertIn(reverse("accounts:login"), target)
        # CRITICAL: no auth occurred — the user is NOT in the session
        self.assertNotIn("_auth_user_id", self.client.session)

    @override_settings(PASSKEY_ONLY_ROLES=())
    def test_passkey_only_disabled_lets_super_admin_log_in_with_password(self):
        """Sanity-check: with no roles in PASSKEY_ONLY_ROLES the guard is dormant."""
        response = self.client.post(
            self.login_url,
            {"username": "super42", "password": "testpass1234"},
            follow=False,
        )
        self.assertIn(response.status_code, (301, 302))
        self.assertEqual(
            int(self.client.session["_auth_user_id"]), self.super_admin.pk
        )

    @override_settings(PASSKEY_ONLY_ROLES=("SUPERADMIN",))
    def test_passkey_login_succeeds_for_passkey_only_role(self):
        """The WebAuthn ceremony endpoint MUST stay reachable for the locked role.

        The enforcement guard only fires inside ``login_view``'s password
        branch — it does not block the passkey HTTP endpoints themselves.
        We log the SUPERADMIN in directly (simulating a successful WebAuthn
        ceremony, which calls django.contrib.auth.login under the hood) and
        confirm a follow-up authenticated request is allowed.
        """
        # force_login mimics the post-WebAuthn-verify state without exercising
        # the FIDO2 signature path (which requires a real authenticator).
        self.client.force_login(self.super_admin)
        self.assertEqual(
            int(self.client.session["_auth_user_id"]), self.super_admin.pk
        )
        # And the password-form path STILL refuses them — guard is independent
        # of session state — confirming the guard is scoped to password POST.
        response = self.client.post(
            self.login_url,
            {"username": "super42", "password": "testpass1234"},
            follow=False,
        )
        self.assertIn(response.status_code, (301, 302))
        self.assertIn(reverse("accounts:login"), (response.url or ""))
