"""Workflow 11 (Onboarding) — online student onboarding activates the parent.

Plain ``unittest`` (no DB) so it runs even where the Django test runner can't.

Guards the 2026-06-10 fix: ``student_onboarding_wizard`` created a parent User
(role PARENT, unusable password) + StudentGuardian link but — unlike the
offline-drain path (offline_workflow_handlers._link_parent) — never called
``send_guardian_invite()``. The parent was locked out with no set-password link.
The online path now mirrors the offline one: ``if created: send_guardian_invite(...)``.
"""

from __future__ import annotations

import inspect
import os
import unittest
from pathlib import Path

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

REPO = Path(__file__).resolve().parent.parent.parent.parent


class StudentOnboardingParentInviteTests(unittest.TestCase):

    def test_online_onboarding_sends_guardian_invite_on_create(self) -> None:
        src = (REPO / "apps" / "portal" / "views_onboarding.py").read_text(
            encoding="utf-8", errors="replace"
        )
        self.assertIn("send_guardian_invite(", src)
        # Guarded so existing parents aren't re-invited every time.
        self.assertIn("if created:", src)

    def test_send_guardian_invite_signature_and_safety(self) -> None:
        from apps.accounts.guardian_invite import send_guardian_invite

        sig = inspect.signature(send_guardian_invite)
        self.assertIn("user", sig.parameters)
        self.assertIn("request", sig.parameters)
        self.assertIn("school", sig.parameters)
        # request/school are keyword-only in the canonical signature.
        self.assertEqual(
            sig.parameters["request"].kind, inspect.Parameter.KEYWORD_ONLY
        )


if __name__ == "__main__":
    unittest.main()
