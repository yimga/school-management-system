"""Tests for the Argon2-first password hasher configuration."""

from __future__ import annotations

from django.conf import settings
from django.contrib.auth.hashers import (
    Argon2PasswordHasher,
    check_password,
    identify_hasher,
    make_password,
)
from django.test import SimpleTestCase


class PasswordHasherConfigTests(SimpleTestCase):
    def test_argon2_is_first(self):
        self.assertEqual(
            settings.PASSWORD_HASHERS[0],
            "django.contrib.auth.hashers.Argon2PasswordHasher",
        )

    def test_pbkdf2_remains_for_legacy_hashes(self):
        # Existing PBKDF2 hashes must still verify; Argon2 is for new hashes.
        self.assertIn(
            "django.contrib.auth.hashers.PBKDF2PasswordHasher",
            settings.PASSWORD_HASHERS,
        )

    def test_make_password_produces_argon2_hash(self):
        hashed = make_password("correct horse battery staple")
        # Argon2 hashes start with "argon2"
        self.assertTrue(hashed.startswith("argon2"), f"unexpected hash prefix: {hashed[:12]}")

    def test_argon2_hash_round_trips(self):
        hashed = make_password("test-password-123")
        self.assertTrue(check_password("test-password-123", hashed))
        self.assertFalse(check_password("wrong-password", hashed))

    def test_argon2_hasher_is_importable(self):
        # If argon2-cffi were missing, identify_hasher on an argon2 hash would raise.
        hashed = make_password("anything")
        h = identify_hasher(hashed)
        self.assertIsInstance(h, Argon2PasswordHasher)

    def test_legacy_pbkdf2_hash_still_verifies(self):
        # Force a PBKDF2 hash to confirm legacy verification still works.
        from django.contrib.auth.hashers import PBKDF2PasswordHasher

        legacy_hash = PBKDF2PasswordHasher().encode("legacy-pwd", salt="abcdefghij")
        self.assertTrue(check_password("legacy-pwd", legacy_hash))
