"""A tenant's CORS origins must not become every tenant's CORS origins.

WHY THIS EXISTS
---------------
``TenantCorsAllowlistMiddleware`` used to do this, once per request::

    settings.CORS_ALLOWED_ORIGINS = _merge_origins(static, tenant_origins)

``settings`` is a process-global. The assignment never reset, and ``static`` was
re-read from the already-mutated value next time, so the list grew monotonically:
after a request for tenant A, every later request in that worker -- for any
tenant -- carried A's origins, then A+B's, and so on. One school naming an
integrator made that integrator a valid CORS origin for every other school in
the process.

It never fired in production only because the middleware is not in MIDDLEWARE
and its own note said to mount it ABOVE tenant resolution, where
``request.school`` is None. That is the trap: "fix the ordering" would have
switched the leak ON.

The first test below is the regression seal and does not need Django's request
cycle -- it drives the middleware directly and asserts the global is untouched.
"""
from __future__ import annotations

from django.conf import settings
from django.http import HttpResponse
from django.test import RequestFactory, SimpleTestCase

from apps.api.middleware_tenant_cors import TenantCorsAllowlistMiddleware


class _FakeSchool:
    pk = 1


class GlobalSettingsAreNeverMutatedTests(SimpleTestCase):
    """The seal: whatever happens, CORS_ALLOWED_ORIGINS is left alone."""

    def setUp(self):
        self.factory = RequestFactory()
        self.before = list(getattr(settings, "CORS_ALLOWED_ORIGINS", []) or [])

    def _run(self, origin, school):
        request = self.factory.get("/api/v1/ping/", HTTP_ORIGIN=origin)
        request.school = school
        mw = TenantCorsAllowlistMiddleware(lambda _r: HttpResponse("ok"))
        return mw(request)

    def test_settings_untouched_when_a_tenant_has_origins(self):
        from apps.api import middleware_tenant_cors as mod

        original = mod._extract_tenant_origins
        mod._extract_tenant_origins = lambda school: ["https://a.example"]
        try:
            self._run("https://a.example", _FakeSchool())
        finally:
            mod._extract_tenant_origins = original

        self.assertEqual(
            list(getattr(settings, "CORS_ALLOWED_ORIGINS", []) or []),
            self.before,
            "the middleware mutated the process-global CORS allowlist again; "
            "that leaks one tenant's origins to every other tenant in the worker",
        )

    def test_granted_only_to_the_tenant_that_configured_it(self):
        """Tenant B must not inherit tenant A's origin, in any order."""
        from apps.api import middleware_tenant_cors as mod

        original = mod._extract_tenant_origins
        by_school = {1: ["https://a.example"], 2: []}
        mod._extract_tenant_origins = lambda school: by_school.get(
            getattr(school, "pk", None), []
        )
        try:
            school_a, school_b = _FakeSchool(), _FakeSchool()
            school_b.pk = 2

            granted = self._run("https://a.example", school_a)
            self.assertEqual(
                granted.get("Access-Control-Allow-Origin"), "https://a.example"
            )

            # Same origin, different tenant, immediately afterwards.
            denied = self._run("https://a.example", school_b)
            self.assertIsNone(
                denied.get("Access-Control-Allow-Origin"),
                "tenant B was granted an origin only tenant A configured",
            )
        finally:
            mod._extract_tenant_origins = original

    def test_vary_origin_is_set_so_caches_do_not_cross_wire_tenants(self):
        from apps.api import middleware_tenant_cors as mod

        original = mod._extract_tenant_origins
        mod._extract_tenant_origins = lambda school: ["https://a.example"]
        try:
            response = self._run("https://a.example", _FakeSchool())
        finally:
            mod._extract_tenant_origins = original
        self.assertIn("Origin", response.get("Vary", ""))

    def test_defers_when_cors_middleware_already_answered(self):
        """Never downgrade or overwrite the static/regex allowlist's decision."""
        from apps.api import middleware_tenant_cors as mod

        original = mod._extract_tenant_origins
        mod._extract_tenant_origins = lambda school: ["https://a.example"]

        def already_allowed(_request):
            resp = HttpResponse("ok")
            resp["Access-Control-Allow-Origin"] = "https://first-party.example"
            return resp

        try:
            request = self.factory.get("/x/", HTTP_ORIGIN="https://a.example")
            request.school = _FakeSchool()
            response = TenantCorsAllowlistMiddleware(already_allowed)(request)
        finally:
            mod._extract_tenant_origins = original

        self.assertEqual(
            response["Access-Control-Allow-Origin"], "https://first-party.example"
        )

    def test_unknown_origin_is_not_granted(self):
        from apps.api import middleware_tenant_cors as mod

        original = mod._extract_tenant_origins
        mod._extract_tenant_origins = lambda school: ["https://a.example"]
        try:
            response = self._run("https://evil.example", _FakeSchool())
        finally:
            mod._extract_tenant_origins = original
        self.assertIsNone(response.get("Access-Control-Allow-Origin"))

    def test_no_origin_header_is_a_no_op(self):
        request = self.factory.get("/x/")
        request.school = _FakeSchool()
        response = TenantCorsAllowlistMiddleware(lambda _r: HttpResponse("ok"))(request)
        self.assertIsNone(response.get("Access-Control-Allow-Origin"))
