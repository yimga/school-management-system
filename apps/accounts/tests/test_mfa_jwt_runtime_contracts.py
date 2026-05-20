"""JWT + MFA runtime contracts (expiry, refresh rotation, MFA middleware)."""

from __future__ import annotations

from datetime import timedelta

from django.test import SimpleTestCase
from django.urls import NoReverseMatch, reverse

from apps.accounts.mfa_defaults import BASELINE_REQUIRED_ROLES, role_requires_mfa


class MfaJwtRuntimeContractTests(SimpleTestCase):
    def test_simple_jwt_lifetimes_and_rotation(self):
        from django.conf import settings

        jwt_cfg = getattr(settings, "SIMPLE_JWT", {})
        self.assertIn("ACCESS_TOKEN_LIFETIME", jwt_cfg)
        self.assertIn("REFRESH_TOKEN_LIFETIME", jwt_cfg)
        self.assertLessEqual(jwt_cfg["ACCESS_TOKEN_LIFETIME"], timedelta(hours=24))
        self.assertGreaterEqual(jwt_cfg["REFRESH_TOKEN_LIFETIME"], timedelta(days=1))
        self.assertTrue(jwt_cfg.get("ROTATE_REFRESH_TOKENS"))
        self.assertTrue(jwt_cfg.get("BLACKLIST_AFTER_ROTATION"))

    def test_token_blacklist_app_installed(self):
        from django.conf import settings

        self.assertIn(
            "rest_framework_simplejwt.token_blacklist",
            settings.INSTALLED_APPS,
        )

    def test_jwt_auth_endpoints_resolve(self):
        for name in ("api:token_obtain_pair", "api:token_refresh"):
            try:
                path = reverse(name)
            except NoReverseMatch as exc:
                self.fail(f"{name} did not resolve: {exc}")
            self.assertTrue(path.startswith("/api/"))

    def test_mfa_middleware_wired(self):
        from django.conf import settings

        self.assertIn(
            "apps.accounts.middleware.RequireMFAMiddleware",
            settings.MIDDLEWARE,
        )

    def test_high_risk_roles_require_mfa(self):
        for role in ("SUPER_ADMIN", "FINANCE_ADMIN", "SCHOOL_ADMIN"):
            self.assertIn(role, BASELINE_REQUIRED_ROLES)
            self.assertTrue(role_requires_mfa(role, None))
