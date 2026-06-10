"""S3 (MFA/SSO/auth) — claim_invite() must pass an explicit login() backend.

Plain ``unittest`` (no DB) so it runs even where the Django test runner can't.

Guards the 2026-06-10 fix: ``claim_invite`` builds a brand-new parent User via
``ClaimInviteAccountForm.save_user()`` (which calls ``User.objects.create_user``
and returns the user WITHOUT running ``authenticate()``), then logged it in with
a bare ``login(request, user)``. With 3 entries in AUTHENTICATION_BACKENDS and no
``user.backend`` attribute, Django's ``login()`` raises
``ValueError: You have multiple authentication backends configured ...`` — a hard
500 on EVERY successful guardian claim-invite submission. The call now passes an
explicit ``backend=`` (vanilla ModelBackend), matching the SAML/OIDC login calls.
"""

from __future__ import annotations

import ast
import os
import unittest
from pathlib import Path

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

REPO = Path(__file__).resolve().parent.parent.parent.parent


class ClaimInviteLoginBackendTests(unittest.TestCase):

    def _claim_invite_body(self) -> str:
        src = (REPO / "apps" / "accounts" / "views.py").read_text(
            encoding="utf-8", errors="replace"
        )
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "claim_invite":
                return ast.get_source_segment(src, node)
        self.fail("claim_invite() not found in apps/accounts/views.py")

    def test_login_call_passes_explicit_backend(self) -> None:
        body = self._claim_invite_body()
        self.assertIn("login(request, user", body)
        # The bare two-arg call would 500; require the explicit backend kwarg.
        self.assertIn("backend=", body)
        self.assertNotIn(
            "login(request, user)", body,
            "bare login(request, user) re-introduces the multi-backend ValueError 500",
        )

    def test_save_user_does_not_set_backend(self) -> None:
        # If this ever changes (save_user starts authenticating / setting
        # user.backend), the explicit kwarg becomes redundant but harmless —
        # this test documents WHY the kwarg is required today.
        forms_src = (REPO / "apps" / "accounts" / "forms.py").read_text(
            encoding="utf-8", errors="replace"
        )
        tree = ast.parse(forms_src)
        save_user_body = None
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "save_user":
                save_user_body = ast.get_source_segment(forms_src, node)
                break
        self.assertIsNotNone(save_user_body)
        self.assertIn("create_user(", save_user_body)
        self.assertNotIn(".backend", save_user_body)

    def test_three_backends_configured(self) -> None:
        from django.conf import settings

        self.assertGreater(
            len(settings.AUTHENTICATION_BACKENDS), 1,
            "multi-backend is the precondition that makes the explicit backend= required",
        )


if __name__ == "__main__":
    unittest.main()
