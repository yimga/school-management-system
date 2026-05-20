"""CORS/CSRF runtime contracts for multi-tenant hosts (repo-scope)."""

from __future__ import annotations

import re

from django.test import SimpleTestCase, override_settings


class CorsCsrfTenantRuntimeTests(SimpleTestCase):
    def test_cors_allow_all_disabled(self):
        from django.conf import settings

        self.assertFalse(getattr(settings, "CORS_ALLOW_ALL_ORIGINS", False))

    def test_cors_regex_https_subdomain_only(self):
        from django.conf import settings

        patterns = list(getattr(settings, "CORS_ALLOWED_ORIGIN_REGEXES", []) or [])
        for pattern in patterns:
            self.assertTrue(
                pattern.startswith("^https://"),
                f"CORS regex must be HTTPS-only: {pattern!r}",
            )
            self.assertNotIn("*", pattern.replace("[a-z0-9-]+", ""))

    def test_csrf_trusted_origins_no_bare_wildcard_scheme(self):
        from django.conf import settings

        for origin in getattr(settings, "CSRF_TRUSTED_ORIGINS", []) or []:
            self.assertFalse(origin in ("*", "https://*"))
            if origin.startswith("https://*."):
                self.assertIn(
                    settings.MULTI_TENANT_BASE_DOMAIN,
                    origin,
                    "subdomain CSRF wildcard must match configured base domain",
                )

    @override_settings(
        MULTI_TENANT_BASE_DOMAIN="runmycampus.com",
        CSRF_TRUSTED_ORIGINS=["https://manager.runmycampus.com"],
        CORS_ALLOWED_ORIGIN_REGEXES=[r"^https://[a-z0-9-]+\.runmycampus\.com$"],
    )
    def test_tenant_subdomain_matches_cors_regex(self):
        from django.conf import settings

        origin = "https://demo-school.runmycampus.com"
        matched = any(re.match(p, origin) for p in settings.CORS_ALLOWED_ORIGIN_REGEXES)
        self.assertTrue(matched)

    def test_manager_csrf_cookie_isolated_from_default(self):
        from django.conf import settings

        self.assertNotEqual(
            getattr(settings, "CSRF_COOKIE_NAME", "csrftoken"),
            getattr(settings, "MANAGER_CSRF_COOKIE_NAME", ""),
        )
