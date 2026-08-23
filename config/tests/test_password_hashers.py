"""Tests for the Argon2-first password hasher configuration.

WHY THESE PIN THE CONFIGURATION EXPLICITLY
------------------------------------------
``config/settings_test.py`` replaces PASSWORD_HASHERS with MD5 so the suite is not
spending its life deriving Argon2 hashes. That is correct and should stay. But it
means five of these tests -- everything asserting Argon2 -- could not pass under
ANY test-settings run: they read the ambient ``settings.PASSWORD_HASHERS``, which
under test is deliberately not the production value. They were red locally forever
and only ever green in CI, which runs ``config.settings``.

A guard that can only pass on one machine is not a guard. So the behavioural tests
now declare the configuration they are exercising with ``override_settings``, and
the configuration test reads ``config/settings.py`` SOURCE -- the same approach the
middleware-ordering tests take, and for the same reason: the live object is not the
thing under test.

``PRODUCTION_HASHERS`` is parsed from the settings module rather than hardcoded, so
this cannot drift into asserting a list the platform no longer ships.
"""

from __future__ import annotations

import ast
import pathlib

from django.contrib.auth.hashers import (
    Argon2PasswordHasher,
    check_password,
    identify_hasher,
    make_password,
)
from django.test import SimpleTestCase, override_settings

_SETTINGS = pathlib.Path(__file__).resolve().parents[2] / "config" / "settings.py"

_ARGON2 = "django.contrib.auth.hashers.Argon2PasswordHasher"
_PBKDF2 = "django.contrib.auth.hashers.PBKDF2PasswordHasher"


def _production_hashers() -> list[str]:
    """PASSWORD_HASHERS as config/settings.py declares it, not as tests override it."""
    tree = ast.parse(_SETTINGS.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id == "PASSWORD_HASHERS":
                return [
                    e.value
                    for e in ast.walk(node.value)
                    if isinstance(e, ast.Constant) and isinstance(e.value, str)
                ]
    return []


PRODUCTION_HASHERS = _production_hashers()


class PasswordHasherConfigTests(SimpleTestCase):
    def test_the_production_list_was_parsed(self):
        # Calibration: an empty list would make both assertions below vacuous.
        self.assertGreater(len(PRODUCTION_HASHERS), 1, PRODUCTION_HASHERS)

    def test_argon2_is_first(self):
        self.assertEqual(PRODUCTION_HASHERS[0], _ARGON2)

    def test_pbkdf2_remains_for_legacy_hashes(self):
        # Existing PBKDF2 hashes must still verify; Argon2 is for new hashes.
        self.assertIn(_PBKDF2, PRODUCTION_HASHERS)


@override_settings(PASSWORD_HASHERS=[_ARGON2, _PBKDF2])
class PasswordHasherBehaviourTests(SimpleTestCase):
    """Exercised against the PRODUCTION hasher list, declared here explicitly.

    Without the override these run under the suite's MD5 setting and assert
    Argon2, which can never hold.
    """

    def test_make_password_produces_argon2_hash(self):
        hashed = make_password("correct horse battery staple")
        self.assertTrue(
            hashed.startswith("argon2"), f"unexpected hash prefix: {hashed[:12]}"
        )

    def test_argon2_hash_round_trips(self):
        hashed = make_password("test-password-123")
        self.assertTrue(check_password("test-password-123", hashed))
        self.assertFalse(check_password("wrong-password", hashed))

    def test_argon2_hasher_is_importable(self):
        # If argon2-cffi were missing, identify_hasher on an argon2 hash would raise.
        hashed = make_password("anything")
        self.assertIsInstance(identify_hasher(hashed), Argon2PasswordHasher)

    def test_legacy_pbkdf2_hash_still_verifies(self):
        # Force a PBKDF2 hash to confirm legacy verification still works.
        from django.contrib.auth.hashers import PBKDF2PasswordHasher

        legacy_hash = PBKDF2PasswordHasher().encode("legacy-pwd", salt="abcdefghij")
        self.assertTrue(check_password("legacy-pwd", legacy_hash))
