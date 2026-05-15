"""Tests for the per-endpoint sliding-window rate limiter."""

from __future__ import annotations

from django.core.cache import cache
from django.http import HttpResponse
from django.test import RequestFactory, SimpleTestCase, override_settings

from apps.security.rate_limit import rate_limit


class RateLimitDecoratorTests(SimpleTestCase):
    def setUp(self):
        cache.clear()
        self.factory = RequestFactory()

    def _make_view(self, **kw):
        @rate_limit(**kw)
        def view(request):
            return HttpResponse("ok", status=200)

        return view

    def test_under_limit_allowed(self):
        view = self._make_view(scope="t1", limit=3, window_seconds=60)
        req = self.factory.get("/x", REMOTE_ADDR="10.0.0.1")
        for _ in range(3):
            self.assertEqual(view(req).status_code, 200)

    def test_over_limit_blocked_with_429(self):
        view = self._make_view(scope="t2", limit=2, window_seconds=60)
        req = self.factory.get("/x", REMOTE_ADDR="10.0.0.2")
        self.assertEqual(view(req).status_code, 200)
        self.assertEqual(view(req).status_code, 200)
        resp = view(req)
        self.assertEqual(resp.status_code, 429)
        self.assertIn("Retry-After", resp)

    def test_distinct_clients_have_independent_counters(self):
        view = self._make_view(scope="t3", limit=1, window_seconds=60)
        req1 = self.factory.get("/x", REMOTE_ADDR="10.0.0.1")
        req2 = self.factory.get("/x", REMOTE_ADDR="10.0.0.2")
        self.assertEqual(view(req1).status_code, 200)
        self.assertEqual(view(req2).status_code, 200)
        self.assertEqual(view(req1).status_code, 429)
        self.assertEqual(view(req2).status_code, 429)

    def test_distinct_scopes_have_independent_counters(self):
        view_a = self._make_view(scope="ta_login", limit=1, window_seconds=60)
        view_b = self._make_view(scope="ta_password_reset", limit=1, window_seconds=60)
        req = self.factory.get("/x", REMOTE_ADDR="10.0.0.5")
        self.assertEqual(view_a(req).status_code, 200)
        self.assertEqual(view_b(req).status_code, 200)
        self.assertEqual(view_a(req).status_code, 429)
        self.assertEqual(view_b(req).status_code, 429)

    @override_settings(RATE_LIMIT_ENABLED=False)
    def test_disabled_globally_via_setting(self):
        view = self._make_view(scope="t4", limit=1, window_seconds=60)
        req = self.factory.get("/x", REMOTE_ADDR="10.0.0.3")
        for _ in range(5):
            self.assertEqual(view(req).status_code, 200)

    def test_custom_key_callable_used(self):
        captured = []

        def custom_key(request):
            captured.append(True)
            return "fixed_id"

        view = self._make_view(
            scope="t5", limit=1, window_seconds=60, key=custom_key
        )
        req = self.factory.get("/x", REMOTE_ADDR="10.0.0.4")
        self.assertEqual(view(req).status_code, 200)
        self.assertEqual(view(req).status_code, 429)
        self.assertEqual(len(captured), 2)
