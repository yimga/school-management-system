"""Never-claimed / inactive account lockout — the gilead-tech report (2026-07-30).

A tenant user (novijonongni@gmail.com on gilead-tech) hit ALL of these at once:
  * login shows "invalid username or password" with correct-looking creds,
  * "forgot password" never emails a reset link,
  * (and so) they can never reach the login-gated MFA-setup page to enroll.

Root cause: an account with NO usable password (created via set_unusable_password
at provisioning / bulk import) that is ALSO is_active=False is invisible to
authenticate(), to the login auto-recovery, AND to the password-reset user
lookup — every door requires is_active=True. It has no password to protect, so
the fix reaches it via the reset/claim link and ACTIVATES it on claim, while a
genuinely-deactivated account (real password + is_active=False) stays locked.

MUST-FIRE tests for that fix.
"""

from __future__ import annotations

from django.contrib.auth.tokens import default_token_generator
from django.core import mail
from django.test import TestCase, override_settings
from django.urls import NoReverseMatch, reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from apps.accounts.models import User
from apps.accounts.password_reset import PortalPasswordResetForm


def _make(username, email, *, usable, active=True):
    u = User.objects.create_user(username=username, email=email, password="seed-pass-1234")
    if not usable:
        u.set_unusable_password()
    u.is_active = active
    u.save()
    return u


class PortalPasswordResetGetUsersTests(TestCase):
    """get_users must reach never-claimed accounts regardless of is_active,
    without re-opening a genuinely-deactivated (real-password) account."""

    def _emails(self, identifier):
        return {u.pk for u in PortalPasswordResetForm().get_users(identifier)}

    def test_active_usable_password_user_included(self):
        u = _make("active_real", "active_real@x.edu", usable=True, active=True)
        self.assertIn(u.pk, self._emails("active_real@x.edu"))

    def test_inactive_never_claimed_user_included(self):
        # The gilead-tech case: no usable password + is_active=False -> was dropped.
        u = _make("novi", "novijonongni@gmail.com", usable=False, active=False)
        self.assertIn(u.pk, self._emails("novijonongni@gmail.com"))
        # username identifier resolves too
        self.assertIn(u.pk, self._emails("novi"))

    def test_active_never_claimed_owner_included(self):
        u = _make("owner_pending", "owner_pending@x.edu", usable=False, active=True)
        self.assertIn(u.pk, self._emails("owner_pending@x.edu"))

    def test_deactivated_real_password_user_excluded(self):
        # Security invariant: disabling an established account still blocks reset.
        _make("disabled_real", "disabled_real@x.edu", usable=True, active=False)
        self.assertEqual(self._emails("disabled_real@x.edu"), set())

    def test_reset_email_is_actually_sent_to_inactive_never_claimed(self):
        _make("novi2", "novi2@gmail.com", usable=False, active=False)
        form = PortalPasswordResetForm(data={"email": "novi2@gmail.com"})
        self.assertTrue(form.is_valid(), form.errors)
        form.save(
            domain_override="testserver",
            email_template_name="emails/password_reset.txt",
            subject_template_name="registration/password_reset_subject.txt",
        )
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("novi2@gmail.com", mail.outbox[0].to)


@override_settings(ROOT_URLCONF="config.urls", ALLOWED_HOSTS=["*"])
class ResetConfirmActivatesOnClaimTests(TestCase):
    """Claiming a never-claimed inactive account via the reset link ACTIVATES it,
    so the owner can actually log in afterwards (not bounced by is_active)."""

    def _confirm_url_pair(self, user):
        uid = urlsafe_base64_encode(force_bytes(user.pk))
        token = default_token_generator.make_token(user)
        try:
            enter = reverse(
                "accounts:password_reset_confirm",
                kwargs={"uidb64": uid, "token": token},
            )
        except NoReverseMatch:
            self.skipTest("accounts:password_reset_confirm not on ROOT_URLCONF")
        return enter

    def test_never_claimed_inactive_user_is_activated_on_password_set(self):
        user = _make("claimme", "claimme@x.edu", usable=False, active=False)
        enter = self._confirm_url_pair(user)
        # Django's confirm view stashes the token in session and redirects to a
        # /.../set-password/ URL where the form is actually posted.
        resp = self.client.get(enter)
        self.assertEqual(resp.status_code, 302)
        set_password_url = resp.url
        resp = self.client.post(
            set_password_url,
            {"new_password1": "Fresh-Pass-9021", "new_password2": "Fresh-Pass-9021"},
        )
        self.assertIn(resp.status_code, (200, 302))
        user.refresh_from_db()
        self.assertTrue(user.is_active, "claiming should activate a never-claimed account")
        self.assertTrue(user.has_usable_password())

    def test_active_user_reset_does_not_touch_is_active(self):
        user = _make("stayactive", "stayactive@x.edu", usable=True, active=True)
        enter = self._confirm_url_pair(user)
        resp = self.client.get(enter)
        self.assertEqual(resp.status_code, 302)
        resp = self.client.post(
            resp.url,
            {"new_password1": "Fresh-Pass-9021", "new_password2": "Fresh-Pass-9021"},
        )
        user.refresh_from_db()
        self.assertTrue(user.is_active)
