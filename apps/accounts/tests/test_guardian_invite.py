"""SimpleTestCase coverage for the guardian set-password invite (no DB).

Locks the contract that an invited parent (unusable password) gets a working
one-time set-password link, and that delivery is best-effort (never raises).
"""
from __future__ import annotations

from unittest import mock

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase


def _fake_user(pk=42, email="parent@example.com"):
    User = get_user_model()
    # Unsaved instance is enough for token generation + link building (no DB).
    return User(pk=pk, email=email, password="!unusable")


class GuardianInviteLinkTests(SimpleTestCase):
    def test_build_link_contains_route_uid_and_token(self):
        from apps.accounts.guardian_invite import build_guardian_setup_link

        link = build_guardian_setup_link(_fake_user(), base_url="https://x.test")
        self.assertTrue(link.startswith("https://x.test/"))
        self.assertIn("/guardian-setup/", link)
        # uidb64 + token are the last two path segments.
        parts = [p for p in link.split("/") if p]
        self.assertGreaterEqual(len(parts[-1]), 1)  # token present

    def test_relative_link_when_no_request_or_base(self):
        from apps.accounts.guardian_invite import build_guardian_setup_link

        link = build_guardian_setup_link(_fake_user(), base_url="")
        self.assertIn("/guardian-setup/", link)


class GuardianInviteSendTests(SimpleTestCase):
    def test_none_user_short_circuits(self):
        from apps.accounts.guardian_invite import send_guardian_invite

        out = send_guardian_invite(None)
        self.assertFalse(out["sent"])
        self.assertEqual(out["reason"], "no_user")

    def test_no_email_short_circuits(self):
        from apps.accounts.guardian_invite import send_guardian_invite

        out = send_guardian_invite(_fake_user(email=""))
        self.assertFalse(out["sent"])
        self.assertEqual(out["reason"], "no_email")

    def test_queues_via_send_transactional(self):
        import apps.accounts.guardian_invite as gi

        with mock.patch(
            "apps.schoolops.email_delivery.send_transactional"
        ) as st:
            out = gi.send_guardian_invite(_fake_user())
        self.assertTrue(out["sent"])
        self.assertEqual(out["reason"], "queued")
        self.assertIn("/guardian-setup/", out["link"])
        st.assert_called_once()

    def test_send_failure_is_swallowed(self):
        import apps.accounts.guardian_invite as gi

        with mock.patch(
            "apps.schoolops.email_delivery.send_transactional",
            side_effect=RuntimeError("smtp down"),
        ):
            out = gi.send_guardian_invite(_fake_user())
        self.assertFalse(out["sent"])
        self.assertEqual(out["reason"], "send_failed")
        # Link is still recorded even though delivery failed.
        self.assertIn("/guardian-setup/", out["link"])
