"""No-DB tests for the read-only impersonation guard (Wave C #4 Phase 3a).

RequestFactory + a stub session/resolver_match — no database needed. Covers the
feature-flag default-off no-op and every branch of the enforcement decision.
"""

from __future__ import annotations

from types import SimpleNamespace

from django.http import HttpResponseForbidden
from django.test import RequestFactory, SimpleTestCase, override_settings

from apps.accounts.middleware_impersonation_readonly import (
    ReadOnlyImpersonationGuardMiddleware,
)


def _request(method="POST", *, read_only=None, url_name="some_write_view", path="/x/"):
    rf = RequestFactory()
    req = getattr(rf, method.lower())(path)
    if read_only is None:
        req.session = {}
    else:
        req.session = {"impersonation": {"school_id": "s1", "read_only": read_only}}
    req.resolver_match = SimpleNamespace(url_name=url_name)
    return req


class ReadOnlyImpersonationGuardTests(SimpleTestCase):
    def setUp(self):
        self.mw = ReadOnlyImpersonationGuardMiddleware(lambda r: r)

    def _run(self, req):
        return self.mw.process_view(req, lambda r: r, [], {})

    # --- feature flag default OFF ---

    def test_noop_when_flag_off_even_on_readonly_write(self):
        # Default: flag unset -> middleware is a complete no-op.
        req = _request(method="POST", read_only=True)
        self.assertIsNone(self._run(req))

    # --- flag ON behavior ---

    @override_settings(IMPERSONATION_READ_ONLY_ENFORCED=True)
    def test_blocks_write_during_readonly_impersonation(self):
        req = _request(method="POST", read_only=True)
        resp = self._run(req)
        self.assertIsInstance(resp, HttpResponseForbidden)
        self.assertEqual(resp.status_code, 403)

    @override_settings(IMPERSONATION_READ_ONLY_ENFORCED=True)
    def test_allows_safe_method(self):
        req = _request(method="GET", read_only=True)
        self.assertIsNone(self._run(req))

    @override_settings(IMPERSONATION_READ_ONLY_ENFORCED=True)
    def test_allows_write_when_not_impersonating(self):
        req = _request(method="POST", read_only=None)
        self.assertIsNone(self._run(req))

    @override_settings(IMPERSONATION_READ_ONLY_ENFORCED=True)
    def test_allows_write_when_impersonation_not_readonly(self):
        req = _request(method="POST", read_only=False)
        self.assertIsNone(self._run(req))

    @override_settings(IMPERSONATION_READ_ONLY_ENFORCED=True)
    def test_allows_exit_paths_even_when_readonly(self):
        for name in (
            "end_impersonation",
            "impersonation_stop",
            "impersonation_stop_redirect",
            "logout",
            "account_logout",
        ):
            req = _request(method="POST", read_only=True, url_name=name)
            self.assertIsNone(self._run(req), f"{name} must stay reachable")

    @override_settings(IMPERSONATION_READ_ONLY_ENFORCED=True)
    def test_blocks_all_unsafe_methods(self):
        for method in ("POST", "PUT", "PATCH", "DELETE"):
            req = _request(method=method, read_only=True)
            resp = self._run(req)
            self.assertEqual(resp.status_code, 403, f"{method} should be blocked")
