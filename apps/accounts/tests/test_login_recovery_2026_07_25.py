"""Guided recovery for never-activated accounts at the login form (2026-07-25).

Root cause this seals: a self-serve provisioned owner is created with
``set_unusable_password()`` (``schools.tasks.ensure_admin_user_for_school``), so
typing ANY password on ``/authentication/login/`` fails ``authenticate()`` and
the view re-renders (HTTP 200) forever — the "I put in my password and it just
reloads the sign-in page" dead-end reported platform-wide.

These are MUST-FIRE tests: they assert the login view now (a) detects the
never-activated state, (b) emails a working set-password link, and (c) shows a
guided message instead of the generic dead-end — WITHOUT tallying a brute-force
attempt — while leaving an ordinary wrong password completely unchanged.
"""

from __future__ import annotations

from unittest.mock import patch

from django.contrib.messages import get_messages
from django.core import mail
from django.core.cache import cache
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse

from apps.accounts import login_recovery as lr
from apps.accounts.models import User


class FindUnactivatedAccountTests(TestCase):
    def setUp(self):
        cache.clear()

    def _make(self, username, email, *, usable, active=True, role=None):
        u = User.objects.create_user(username=username, email=email, password="seed-pass-1234")
        if not usable:
            u.set_unusable_password()
        if role is not None:
            u.role = role
        u.is_active = active
        u.save()
        return u

    def test_finds_active_unusable_password_by_email_or_username(self):
        u = self._make("owner1", "owner1@x.edu", usable=False)
        self.assertEqual(lr.find_unactivated_account("owner1@x.edu"), u)
        self.assertEqual(lr.find_unactivated_account("OWNER1"), u)  # case-insensitive username

    def test_ignores_account_with_usable_password(self):
        self._make("owner2", "owner2@x.edu", usable=True)
        self.assertIsNone(lr.find_unactivated_account("owner2@x.edu"))

    def test_ignores_inactive_account(self):
        self._make("owner3", "owner3@x.edu", usable=False, active=False)
        self.assertIsNone(lr.find_unactivated_account("owner3@x.edu"))

    def test_ignores_passkey_only_role(self):
        self._make("owner4", "owner4@x.edu", usable=False, role=User.Role.SUPERADMIN)
        with override_settings(PASSKEY_ONLY_ROLES=("SUPERADMIN",)):
            self.assertIsNone(lr.find_unactivated_account("owner4@x.edu"))

    def test_mask_email(self):
        self.assertEqual(lr.mask_email("owner@school.edu"), "o…r@school.edu")
        self.assertEqual(lr.mask_email("ab@school.edu"), "a…@school.edu")
        self.assertEqual(lr.mask_email("not-an-email"), "")


class OfferUnactivatedRecoveryTests(TestCase):
    def setUp(self):
        cache.clear()
        self.owner = User.objects.create_user(
            username="stuckowner", email="stuck@x.edu", password="seed-pass-1234"
        )
        self.owner.set_unusable_password()
        self.owner.save()

    @patch("apps.accounts.login_recovery.send_set_password_link", return_value=True)
    def test_unactivated_sends_once_then_throttled(self, mock_send):
        first = lr.offer_unactivated_recovery(None, "stuck@x.edu")
        self.assertTrue(first["unactivated"])
        self.assertTrue(first["sent"])
        self.assertEqual(mock_send.call_count, 1)

        # Second attempt within the throttle window must NOT resend (no mail bomb).
        second = lr.offer_unactivated_recovery(None, "stuck@x.edu")
        self.assertTrue(second["unactivated"])
        self.assertTrue(second["sent"])  # stays honest ("we've emailed you")
        self.assertEqual(mock_send.call_count, 1)

    @patch("apps.accounts.login_recovery.send_set_password_link", return_value=True)
    def test_activated_user_is_not_offered_recovery(self, mock_send):
        User.objects.create_user(username="real", email="real@x.edu", password="realpass-1234")
        result = lr.offer_unactivated_recovery(None, "real@x.edu")
        self.assertFalse(result["unactivated"])
        mock_send.assert_not_called()

    @override_settings(LOGIN_UNACTIVATED_RECOVERY_ENABLED=False)
    @patch("apps.accounts.login_recovery.send_set_password_link", return_value=True)
    def test_kill_switch_disables_recovery(self, mock_send):
        result = lr.offer_unactivated_recovery(None, "stuck@x.edu")
        self.assertFalse(result["unactivated"])
        mock_send.assert_not_called()

    @patch("apps.accounts.password_reset.PortalPasswordResetForm")
    def test_send_set_password_link_uses_reset_form(self, MockForm):
        form = MockForm.return_value
        form.is_valid.return_value = True
        ok = lr.send_set_password_link(None, self.owner)
        self.assertTrue(ok)
        # Built for the owner's email, and dispatched with the reset templates.
        self.assertEqual(MockForm.call_args.kwargs["data"], {"email": "stuck@x.edu"})
        save_kwargs = form.save.call_args.kwargs
        self.assertEqual(save_kwargs["email_template_name"], "emails/password_reset.txt")
        self.assertEqual(save_kwargs["subject_template_name"], "registration/password_reset_subject.txt")

    def test_offer_actually_produces_a_reset_email(self):
        """PROOF (no patch): a real email with a working reset-confirm link is sent."""
        req = RequestFactory().post("/authentication/login/")
        result = lr.offer_unactivated_recovery(req, "stuck@x.edu")
        self.assertTrue(result["unactivated"])
        self.assertTrue(result["sent"])
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("stuck@x.edu", mail.outbox[0].to)
        # The link is the reset-confirm URL that works for unusable-password owners.
        self.assertIn("/authentication/reset/", mail.outbox[0].body)


@override_settings(RATELIMIT_ENABLE=False)
class LoginViewGuidedRecoveryTests(TestCase):
    """End-to-end through the real login URL + Django test client."""

    def setUp(self):
        cache.clear()
        self.login_url = reverse("accounts:login")
        self.owner = User.objects.create_user(
            username="strandedowner", email="stranded@x.edu", password="seed-pass-1234"
        )
        self.owner.set_unusable_password()
        self.owner.save()

    @patch("apps.accounts.login_recovery.send_set_password_link", return_value=True)
    def test_never_activated_login_guides_instead_of_dead_end(self, mock_send):
        resp = self.client.post(
            self.login_url,
            {"username": "stranded@x.edu", "password": "whatever-they-typed"},
            follow=False,
        )
        # Re-render (200), not a redirect, and NO session established.
        self.assertEqual(resp.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)
        # A working set-password link was emailed.
        mock_send.assert_called_once()
        # NOT tallied as a brute-force password guess (there is no password to guess).
        self.assertEqual(self.client.session.get("auth_failed_attempts", 0), 0)
        # Guided message, not the generic dead-end.
        msgs = [str(m) for m in get_messages(resp.wsgi_request)]
        self.assertTrue(any("set a password yet" in m for m in msgs), msgs)
        self.assertFalse(any("Invalid username or password" in m for m in msgs), msgs)

    @patch("apps.accounts.login_recovery.send_set_password_link", return_value=True)
    def test_wrong_password_for_activated_user_is_unchanged(self, mock_send):
        User.objects.create_user(
            username="realuser", email="real@x.edu", password="correcthorse-1234"
        )
        resp = self.client.post(
            self.login_url,
            {"username": "real@x.edu", "password": "definitely-wrong"},
            follow=False,
        )
        self.assertEqual(resp.status_code, 200)
        mock_send.assert_not_called()  # activated user → no recovery offered
        self.assertEqual(self.client.session.get("auth_failed_attempts", 0), 1)  # still tallied
        msgs = [str(m) for m in get_messages(resp.wsgi_request)]
        self.assertTrue(any("Invalid username or password" in m for m in msgs), msgs)

    @patch("apps.accounts.login_recovery.send_set_password_link", return_value=True)
    def test_guided_message_renders_visibly_in_the_card(self, mock_send):
        """The guidance must render INSIDE the auth card (the base copy is hidden)."""
        resp = self.client.post(
            self.login_url,
            {"username": "stranded@x.edu", "password": "whatever"},
            follow=False,
        )
        self.assertContains(resp, "rmc-auth-immersive__messages", status_code=200)
        self.assertContains(resp, "set a password yet")

    @patch("apps.accounts.login_recovery.send_set_password_link", return_value=True)
    @patch("apps.accounts.login_guard.lockout_state", return_value=(True, 300))
    def test_locked_never_activated_owner_still_gets_recovery(self, _lock, mock_send):
        """A rate-limited stranded owner must still be recovered, not walled off."""
        resp = self.client.post(
            self.login_url,
            {"username": "stranded@x.edu", "password": "whatever"},
            follow=False,
        )
        self.assertEqual(resp.status_code, 200)
        mock_send.assert_called_once()  # recovery offered DESPITE the lockout
        msgs = [str(m) for m in get_messages(resp.wsgi_request)]
        self.assertTrue(any("set a password yet" in m for m in msgs), msgs)
        # The dead "too many attempts" wall is suppressed for never-activated accounts.
        self.assertFalse(any("Too many failed" in m for m in msgs), msgs)

    @patch("apps.accounts.login_guard.lockout_state", return_value=(True, 300))
    def test_locked_activated_user_still_sees_lockout_wall(self, _lock):
        """Refactor must NOT weaken the lockout wall for a normal (activated) user."""
        User.objects.create_user(
            username="realuser2", email="real2@x.edu", password="correcthorse-1234"
        )
        resp = self.client.post(
            self.login_url,
            {"username": "real2@x.edu", "password": "whatever"},
            follow=False,
        )
        self.assertEqual(resp.status_code, 200)
        msgs = [str(m) for m in get_messages(resp.wsgi_request)]
        self.assertTrue(any("Too many failed" in m for m in msgs), msgs)

    @override_settings(LOGIN_POW_ENABLED=True)
    @patch("apps.accounts.login_recovery.send_set_password_link", return_value=True)
    @patch("apps.accounts.login_guard.attempt_count", return_value=2)
    def test_challenge_blocked_never_activated_owner_still_gets_recovery(self, _cnt, mock_send):
        """A never-activated owner stopped at the PoW challenge is still recovered.

        prior_miss (attempt_count>=1) + PoW enabled + no solved pow_token ⇒
        verify_pow fails ⇒ login_block_reason='challenge'. Recovery must still fire
        (there is no password to challenge) and the "verification challenge" wall
        must be suppressed for this account.
        """
        resp = self.client.post(
            self.login_url,
            {"username": "stranded@x.edu", "password": "whatever"},  # no pow_token/nonce
            follow=False,
        )
        self.assertEqual(resp.status_code, 200)
        mock_send.assert_called_once()  # recovery offered DESPITE the challenge wall
        msgs = [str(m) for m in get_messages(resp.wsgi_request)]
        self.assertTrue(any("set a password yet" in m for m in msgs), msgs)
        self.assertFalse(any("verification challenge" in m for m in msgs), msgs)
