"""Tests for the Content-Security-Policy middleware + report endpoint."""

from __future__ import annotations

import json

from django.http import HttpResponse
from django.test import RequestFactory, SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from apps.security.csp_middleware import (
    ContentSecurityPolicyMiddleware,
    _build_policy,
)


def _get_response(request):
    return HttpResponse("<html>ok</html>", content_type="text/html")


class CspMiddlewareTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()

    @override_settings(CSP_ENFORCE=True)
    def test_html_response_gets_csp_enforce_header_by_default(self):
        """CSP_ENFORCE defaults True since v2.57 (inline-style backlog at 0)."""
        mw = ContentSecurityPolicyMiddleware(_get_response)
        resp = mw(self.factory.get("/"))
        self.assertIn("Content-Security-Policy", resp)
        self.assertNotIn("Content-Security-Policy-Report-Only", resp)
        self.assertIn("default-src 'self'", resp["Content-Security-Policy"])

    @override_settings(CSP_ENFORCE=False)
    def test_html_response_gets_report_only_when_enforce_disabled(self):
        mw = ContentSecurityPolicyMiddleware(_get_response)
        resp = mw(self.factory.get("/"))
        self.assertIn("Content-Security-Policy-Report-Only", resp)
        self.assertNotIn("Content-Security-Policy", resp)
        self.assertIn("default-src 'self'", resp["Content-Security-Policy-Report-Only"])

    def test_admin_path_bypassed(self):
        mw = ContentSecurityPolicyMiddleware(_get_response)
        resp = mw(self.factory.get("/admin/login/"))
        self.assertNotIn("Content-Security-Policy-Report-Only", resp)
        self.assertNotIn("Content-Security-Policy", resp)

    @override_settings(CSP_ENFORCE=True)
    def test_static_path_bypassed(self):
        mw = ContentSecurityPolicyMiddleware(_get_response)
        resp = mw(self.factory.get("/static/css/x.css"))
        self.assertNotIn("Content-Security-Policy-Report-Only", resp)

    def test_non_html_response_not_decorated(self):
        def json_response(request):
            return HttpResponse('{"ok": true}', content_type="application/json")

        mw = ContentSecurityPolicyMiddleware(json_response)
        resp = mw(self.factory.get("/api/x"))
        self.assertNotIn("Content-Security-Policy-Report-Only", resp)

    @override_settings(
        CSP_EXTRA_SCRIPT_SRC=("https://cdn.example.com",),
        CSP_REPORT_URI="/security/csp-report/",
    )
    def test_extra_origins_appear_in_policy(self):
        policy = _build_policy()
        self.assertIn("https://cdn.example.com", policy)
        self.assertIn("report-uri /security/csp-report/", policy)

    def test_default_policy_is_self_only(self):
        policy = _build_policy()
        self.assertIn("default-src 'self'", policy)
        self.assertIn("script-src 'self'", policy)
        self.assertIn("frame-ancestors 'self'", policy)
        self.assertIn("object-src 'none'", policy)


class CspReportEndpointTests(TestCase):
    def test_valid_legacy_report_returns_204(self):
        body = json.dumps({
            "csp-report": {
                "violated-directive": "script-src",
                "blocked-uri": "inline",
                "document-uri": "https://example.test/page",
            }
        }).encode("utf-8")
        url = reverse("csp_violation_report")
        resp = self.client.post(url, data=body, content_type="application/json")
        self.assertEqual(resp.status_code, 204)

    def test_modern_reporting_api_payload_returns_204(self):
        body = json.dumps({
            "violated-directive": "img-src",
            "blocked-uri": "https://tracker.example/x.gif",
        }).encode("utf-8")
        url = reverse("csp_violation_report")
        resp = self.client.post(url, data=body, content_type="application/json")
        self.assertEqual(resp.status_code, 204)

    def test_invalid_json_returns_400(self):
        url = reverse("csp_violation_report")
        resp = self.client.post(url, data=b"not-json", content_type="application/json")
        self.assertEqual(resp.status_code, 400)

    def test_get_method_not_allowed(self):
        url = reverse("csp_violation_report")
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 405)
