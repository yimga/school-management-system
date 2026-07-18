"""Password reset must email a WORKING link, not a blank one.

Regression seal for a shipped, security-critical bug: ``PortalPasswordResetForm``
overrides ``__init__`` / ``send_mail`` / ``get_users`` but **not** ``save()``, so
the branded templates (``emails/password_reset.{txt,html}``) received Django's
stock context (``uid``/``token``/``protocol``/``domain``/``user``/``email``/
``site_name``) while referencing ``reset_url`` / ``user_name`` / ``school_name``
/ ``expiry_hours``. With ``string_if_invalid`` at Django's default (``""``),
``{{ reset_url }}`` rendered EMPTY — so the reset email shipped a blank link and
no recipient could ever complete a password reset. The fix populates those keys
in ``send_mail`` from the per-user ``uid``/``token``/``protocol``/``domain``.
"""

from __future__ import annotations

import re

from django.core import mail
from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import User


class PasswordResetEmailLinkTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="reset_owner",
            email="reset_owner@example.com",
            password="OldPass!234",
        )

    def _request_reset(self):
        return self.client.post(
            reverse("accounts:password_reset"),
            {"email": "reset_owner@example.com"},
        )

    def test_reset_email_carries_a_nonblank_resolvable_link(self):
        """The bug: the line after 'Reset your password:' was blank."""
        resp = self._request_reset()
        self.assertEqual(resp.status_code, 302)  # -> accounts:password_reset_done
        self.assertEqual(len(mail.outbox), 1)
        body = mail.outbox[0].body

        match = re.search(r"/authentication/reset/[^/\s]+/[^/\s]+/", body)
        self.assertIsNotNone(
            match,
            "reset email body has no confirm link -- {{ reset_url }} rendered "
            "empty (the blank-link bug)",
        )
        confirm_path = match.group(0)

        # And the link must actually resolve to the set-password form, on the
        # host the test client used (the confirm route resolves on every host).
        followed = self.client.get(confirm_path, follow=True)
        self.assertEqual(followed.status_code, 200)
        self.assertContains(followed, "new_password1")

    def test_reset_email_greets_user_and_states_a_real_expiry(self):
        """user_name + expiry_hours used to render empty ('Hello ,' / 'in  hour(s)')."""
        self._request_reset()
        self.assertEqual(len(mail.outbox), 1)
        body = mail.outbox[0].body
        self.assertNotIn("Hello ,", body)
        self.assertIn("reset_owner", body)  # user_name falls back to the username
        self.assertRegex(body, r"expires in \d+ hour")
