"""Auth runtime boundaries: DRF defaults, hashers, JWT, no permissive API defaults."""

from __future__ import annotations

from django.test import SimpleTestCase


class AuthRuntimeBoundaryTests(SimpleTestCase):
    def test_drf_default_permission_is_authenticated(self):
        from django.conf import settings

        perms = settings.REST_FRAMEWORK.get("DEFAULT_PERMISSION_CLASSES", ())
        self.assertTrue(
            any("IsAuthenticated" in p for p in perms),
            f"expected IsAuthenticated default, got {perms!r}",
        )

    def test_drf_includes_jwt_authentication(self):
        from django.conf import settings

        auth = settings.REST_FRAMEWORK.get("DEFAULT_AUTHENTICATION_CLASSES", ())
        self.assertTrue(
            any("JWTAuthentication" in p for p in auth),
            f"expected JWTAuthentication, got {auth!r}",
        )

    def test_password_hashers_prefer_strong_algorithms(self):
        from django.conf import settings

        hashers = list(settings.PASSWORD_HASHERS)
        self.assertTrue(hashers)
        primary = hashers[0]
        self.assertTrue(
            any(
                token in primary
                for token in (
                    "Argon2PasswordHasher",
                    "PBKDF2PasswordHasher",
                    "ScryptPasswordHasher",
                )
            ),
            f"unexpected primary hasher: {primary!r}",
        )

    def test_session_cookie_secure_follows_debug_and_test_gate(self):
        from django.conf import settings

        if settings.DEBUG or getattr(settings, "RUNNING_TESTS", False):
            self.assertFalse(settings.SESSION_COOKIE_SECURE)
            self.assertFalse(settings.CSRF_COOKIE_SECURE)
        else:
            self.assertTrue(settings.SESSION_COOKIE_SECURE)
            self.assertTrue(settings.CSRF_COOKIE_SECURE)
