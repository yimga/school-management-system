"""Wave L-followup: CSP cache-backed violation counter tests.

Covers:

1. The report endpoint increments the per-hour total + per-directive
   counters when a valid CSP violation report is posted.
2. The counter reader aggregates correctly across a multi-hour window.
3. Empty / no-violations state returns 0 (not raise).
4. The readiness preflight surfaces the runtime counts in its report
   but does NOT change `ready` / `issue_count` based on them.
"""

from __future__ import annotations

import json
from unittest import mock

from django.core.cache import cache
from django.test import Client, TestCase, override_settings

from apps.security.csp_violation_counter import (
    violations_by_directive_in_last_hours,
    violations_in_last_hours,
)


_MW_TARGET = "apps.security.csp_middleware.ContentSecurityPolicyMiddleware"


class CounterReaderTests(TestCase):
    """Reader behavior in isolation (no endpoint hits)."""

    def setUp(self):
        cache.clear()

    def test_empty_state_returns_zero(self):
        self.assertEqual(violations_in_last_hours(hours=24), 0)
        self.assertEqual(violations_by_directive_in_last_hours(hours=24), {})

    def test_zero_or_negative_window_returns_empty(self):
        self.assertEqual(violations_in_last_hours(hours=0), 0)
        self.assertEqual(violations_in_last_hours(hours=-3), 0)
        self.assertEqual(violations_by_directive_in_last_hours(hours=0), {})

    def test_seeded_counters_aggregate(self):
        # Seed the current-hour bucket directly to mirror what the writer
        # would have done.
        from apps.security.csp_violation_counter import _current_hour_bucket
        bucket = _current_hour_bucket()
        cache.set(f"csp_violations:bucket:{bucket}", 5, 60)
        cache.set(f"csp_violations:directive:{bucket}:script-src", 3, 60)
        cache.set(f"csp_violations:directive:{bucket}:style-src", 2, 60)

        self.assertEqual(violations_in_last_hours(hours=1), 5)
        by_directive = violations_by_directive_in_last_hours(hours=1)
        self.assertEqual(by_directive, {"script-src": 3, "style-src": 2})

    def test_reader_swallows_cache_backend_error(self):
        with mock.patch(
            "apps.security.csp_violation_counter.cache.get",
            side_effect=RuntimeError("cache down"),
        ):
            self.assertEqual(violations_in_last_hours(hours=24), 0)


class ReportEndpointWritesCounterTests(TestCase):
    """The endpoint must increment cache counters on a valid report."""

    def setUp(self):
        cache.clear()
        self.client = Client()

    def _post_violation(self, directive: str = "script-src"):
        payload = {
            "csp-report": {
                "violated-directive": directive,
                "blocked-uri": "https://evil.example/x.js",
                "document-uri": "https://tenant.runmycampus.com/dashboard",
            }
        }
        return self.client.post(
            "/security/csp-report/",
            data=json.dumps(payload),
            content_type="application/csp-report",
        )

    def test_valid_report_increments_total_counter(self):
        self.assertEqual(violations_in_last_hours(hours=1), 0)
        resp = self._post_violation()
        self.assertEqual(resp.status_code, 204)
        self.assertEqual(violations_in_last_hours(hours=1), 1)

    def test_valid_report_increments_per_directive_counter(self):
        self._post_violation(directive="script-src")
        self._post_violation(directive="script-src")
        self._post_violation(directive="style-src")
        by_directive = violations_by_directive_in_last_hours(hours=1)
        self.assertEqual(by_directive.get("script-src"), 2)
        self.assertEqual(by_directive.get("style-src"), 1)

    def test_invalid_json_does_not_increment(self):
        resp = self.client.post(
            "/security/csp-report/",
            data="not-json",
            content_type="application/csp-report",
        )
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(violations_in_last_hours(hours=1), 0)

    def test_directive_normalised_to_first_word(self):
        # "script-src 'nonce-xyz'" should bucket as "script-src".
        self._post_violation(directive="script-src 'nonce-abc123'")
        by_directive = violations_by_directive_in_last_hours(hours=1)
        self.assertEqual(by_directive.get("script-src"), 1)


@override_settings(
    MIDDLEWARE=(_MW_TARGET,),
    CSP_REPORT_URI="/security/csp-report/",
    CSP_EXTRA_SCRIPT_SRC=(),
    CSP_EXTRA_STYLE_SRC=(),
    CSP_EXTRA_IMG_SRC=(),
    CSP_EXTRA_CONNECT_SRC=(),
    CSP_EXTRA_FRAME_ANCESTORS=(),
)
class ReadinessReportSurfacesCountersTests(TestCase):
    """The readiness report includes runtime counters; they don't gate
    `ready` / `issue_count`.
    """

    def setUp(self):
        cache.clear()

    def test_counters_appear_in_report(self):
        # Seed two violations.
        from apps.security.csp_violation_counter import _current_hour_bucket
        bucket = _current_hour_bucket()
        cache.set(f"csp_violations:bucket:{bucket}", 7, 60)
        cache.set(f"csp_violations:directive:{bucket}:script-src", 7, 60)

        from apps.security.csp_readiness import assess_csp_readiness

        report = assess_csp_readiness()
        self.assertEqual(report.violations_last_hour, 7)
        self.assertEqual(report.violations_last_24h, 7)
        self.assertEqual(report.violations_by_directive_24h.get("script-src"), 7)

    def test_counters_do_not_affect_ready(self):
        # Seed a bunch of violations; readiness should still be True
        # because config preflight is clean.
        from apps.security.csp_violation_counter import _current_hour_bucket
        bucket = _current_hour_bucket()
        cache.set(f"csp_violations:bucket:{bucket}", 999, 60)

        from apps.security.csp_readiness import assess_csp_readiness

        report = assess_csp_readiness()
        self.assertTrue(report.ready)
        self.assertEqual(report.issue_count(), 0)
