"""SimpleTestCase coverage for the unauthenticated signup/trial throttle (no DB).

The full create path is DB-backed (CI). Here we lock down the abuse gate: the
per-IP throttle that protects tenant creation + verification-email send from
being run in a loop (slug squatting / free-tier exhaustion / email spam cannon).
"""
from __future__ import annotations

import json
from unittest import mock

from django.test import RequestFactory, SimpleTestCase, override_settings


class SignupRateLimitTests(SimpleTestCase):
    def setUp(self):
        self.rf = RequestFactory()

    def test_allowed_returns_none(self):
        from apps.schools.signup_views import _signup_rate_limited_response

        req = self.rf.post("/signup/school/")
        with mock.patch(
            "apps.api.rate_limit.throttle_ip_request", return_value=(True, 0)
        ):
            out = _signup_rate_limited_response(
                req, "signup_school", json_response=True
            )
        self.assertIsNone(out)

    def test_blocked_json_returns_429(self):
        from apps.schools.signup_views import _signup_rate_limited_response

        req = self.rf.post("/api/trial/")
        with mock.patch(
            "apps.api.rate_limit.throttle_ip_request", return_value=(False, 60)
        ):
            resp = _signup_rate_limited_response(
                req, "api_trial_school", json_response=True
            )
        self.assertEqual(resp.status_code, 429)
        self.assertEqual(resp["Retry-After"], "60")
        body = json.loads(resp.content)
        self.assertEqual(body["error"], "rate_limited")
        self.assertEqual(body["retry_after"], 60)

    def test_blocked_html_redirects_with_retry_after(self):
        from apps.schools import signup_views

        req = self.rf.post("/signup/school/")
        with mock.patch(
            "apps.api.rate_limit.throttle_ip_request", return_value=(False, 30)
        ), mock.patch.object(signup_views, "messages") as m:
            resp = signup_views._signup_rate_limited_response(
                req, "signup_school", json_response=False
            )
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp["Retry-After"], "30")
        m.error.assert_called_once()

    @override_settings(SIGNUP_MAX_PER_WINDOW=5, SIGNUP_RATE_WINDOW_SECONDS=600)
    def test_reads_configurable_limits(self):
        from apps.schools.signup_views import _signup_rate_limited_response

        req = self.rf.post("/signup/school/")
        with mock.patch(
            "apps.api.rate_limit.throttle_ip_request", return_value=(True, 0)
        ) as t:
            _signup_rate_limited_response(req, "signup_school", json_response=True)
        _, kwargs = t.call_args
        self.assertEqual(kwargs["max_count"], 5)
        self.assertEqual(kwargs["window_seconds"], 600)
