"""v4.00.92 — Unit tests for ``lms_connector_d2l`` (W12+W16+W21+W22).

Mirror of Schoology test surface (no shared scaffolding — each connector
duplicates the pattern by design, so tests duplicate too).

Covers ``exchange_authorization_code_for_token``, ``refresh_access_token``,
``push_grade_live``, and ``_retry_with_backoff`` against fake HTTP.
"""

from __future__ import annotations

import os

from django.test import SimpleTestCase

from apps.integrations_marketplace import lms_connector_d2l as _d2l


class _FakeResp:
    def __init__(self, status_code, body=None, headers=None):
        self.status_code = status_code
        self._body = body if body is not None else {}
        self.headers = headers or {}

    def json(self):
        return self._body


class _NoSleep:
    @staticmethod
    def sleep(_x):
        return None


class _D2LTestBase(SimpleTestCase):
    """Shared scaffolding — env capture, audit-hook stub, no-sleep monkey."""

    def setUp(self):
        self._orig_env = os.environ.get(_d2l.LIVE_OUTBOUND_ENV)
        self._orig_audit = _d2l._record_audit
        self.audit_calls: list[dict] = []

        def _fake_audit(**kw):
            self.audit_calls.append(kw)

        _d2l._record_audit = _fake_audit

        self._orig_time = _d2l._time
        _d2l._time = _NoSleep()

        import requests
        self._requests = requests
        self._orig_post = requests.post
        self._orig_put = requests.put

    def tearDown(self):
        if self._orig_env is None:
            os.environ.pop(_d2l.LIVE_OUTBOUND_ENV, None)
        else:
            os.environ[_d2l.LIVE_OUTBOUND_ENV] = self._orig_env
        _d2l._record_audit = self._orig_audit
        _d2l._time = self._orig_time
        self._requests.post = self._orig_post
        self._requests.put = self._orig_put

    def _enable_live(self):
        os.environ[_d2l.LIVE_OUTBOUND_ENV] = "1"

    def _install_post(self, behavior):
        self._requests.post = behavior

    def _install_put(self, behavior):
        self._requests.put = behavior


class ExchangeAuthorizationCodeTests(_D2LTestBase):

    def test_dry_run_when_env_unset(self):
        """No env -> dry-run dict, no audit row."""
        os.environ.pop(_d2l.LIVE_OUTBOUND_ENV, None)
        result = _d2l.exchange_authorization_code_for_token(
            code="abc", client_id="cid", client_secret="cs",
            redirect_uri="https://example.com/cb",
        )
        self.assertTrue(result.get("dry_run"))
        self.assertEqual(result.get("reason"), "live_outbound_disabled_env_unset")
        self.assertEqual(self.audit_calls, [])

    def test_validation_error_short_circuits(self):
        """Missing required field -> validation_error + audit row."""
        result = _d2l.exchange_authorization_code_for_token(
            code="", client_id="cid", client_secret="cs",
            redirect_uri="https://example.com/cb",
        )
        self.assertEqual(result.get("reason"), "validation_error")
        self.assertFalse(result.get("ok"))
        self.assertEqual(len(self.audit_calls), 1)
        self.assertEqual(self.audit_calls[0]["reason"], "validation_error")

    def test_happy_success_via_fake_post(self):
        """Live + 200 -> ok=True + audit ok=True + token hashes only."""
        self._enable_live()
        fake_body = {
            "access_token": "d2l.fake.access",
            "refresh_token": "d2l.fake.refresh",
            "expires_in": 3600,
            "token_type": "Bearer",
            "scope": "core:*:*",
        }

        def _fake_post(*_args, **_kw):
            return _FakeResp(200, body=fake_body)

        self._install_post(_fake_post)
        result = _d2l.exchange_authorization_code_for_token(
            code="auth-code", client_id="cid", client_secret="cs",
            redirect_uri="https://example.com/cb",
            tenant_schema="acme",
        )
        self.assertTrue(result.get("ok"))
        self.assertIn("issued_at_iso", result)
        self.assertEqual(len(self.audit_calls), 1)
        self.assertTrue(self.audit_calls[0]["ok"])
        ps = self.audit_calls[0].get("payload_summary") or {}
        # Verify hashes only, NEVER raw tokens.
        self.assertNotIn("access_token", ps)
        self.assertNotIn("refresh_token", ps)
        self.assertIn("access_token_hash", ps)


class RefreshAccessTokenTests(_D2LTestBase):

    def test_dry_run_when_env_unset(self):
        """Env unset -> dry-run refresh response."""
        os.environ.pop(_d2l.LIVE_OUTBOUND_ENV, None)
        result = _d2l.refresh_access_token(
            refresh_token="rt", client_id="cid", client_secret="cs",
        )
        self.assertTrue(result.get("dry_run"))
        self.assertEqual(result.get("reason"), "live_outbound_disabled_env_unset")

    def test_happy_refresh_success(self):
        """Live + 200 -> ok=True + at least one audit row (refresh action)."""
        self._enable_live()
        fake_body = {
            "access_token": "rotated.access",
            "refresh_token": "rotated.refresh",
            "expires_in": 3600,
            "token_type": "Bearer",
        }

        def _fake_post(*_args, **_kw):
            return _FakeResp(200, body=fake_body)

        self._install_post(_fake_post)
        result = _d2l.refresh_access_token(
            refresh_token="old-rt", client_id="cid", client_secret="cs",
            tenant_schema="acme",
        )
        self.assertTrue(result.get("ok"))
        self.assertIn("issued_at_iso", result)
        actions = [c["action"] for c in self.audit_calls]
        # Refresh row must appear (rotation row may or may not — depends on
        # which Wave-24 wiring is active for D2L).
        self.assertIn("oauth_refresh", actions)
        # All recorded audit calls report success.
        for c in self.audit_calls:
            self.assertTrue(c["ok"])


class PushGradeLiveTests(_D2LTestBase):

    def test_dry_run_when_env_unset(self):
        """Env unset -> dry-run shape echoing intended target_url."""
        os.environ.pop(_d2l.LIVE_OUTBOUND_ENV, None)
        result = _d2l.push_grade_live(
            access_token="at", org_unit_id="ou1", grade_object_id="g1",
            user_id="u1", score=85.0, max_score=100.0,
        )
        self.assertTrue(result.get("dry_run"))
        self.assertEqual(result.get("reason"), "live_outbound_disabled_env_unset")
        self.assertIn("ou1", result.get("target_url", ""))

    def test_happy_200_returns_ok(self):
        """Live + 200 PUT -> ok=True + audit ok=True."""
        self._enable_live()

        def _fake_put(*_args, **_kw):
            return _FakeResp(200, body={"ok": True})

        self._install_put(_fake_put)
        result = _d2l.push_grade_live(
            access_token="at", org_unit_id="ou1", grade_object_id="g1",
            user_id="u1", score=85.0, max_score=100.0,
            tenant_schema="acme",
        )
        self.assertTrue(result.get("ok"))
        self.assertEqual(result.get("http_status"), 200)
        self.assertEqual(len(self.audit_calls), 1)
        self.assertEqual(self.audit_calls[0]["action"], "push_grade_live")


class RetryWithBackoffTests(_D2LTestBase):

    def test_timeout_then_success_retries(self):
        """Timeout once, then 200 -> succeed on attempt 2."""
        import requests
        calls = {"n": 0}

        def _flaky():
            calls["n"] += 1
            if calls["n"] == 1:
                raise requests.Timeout("simulated timeout")
            return _FakeResp(200, body={"ok": True})

        resp = _d2l._retry_with_backoff(_flaky, max_attempts=3, base_delay=0.0)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(calls["n"], 2)

    def test_4xx_does_not_retry(self):
        """4xx returns immediately on first attempt (no retry)."""
        calls = {"n": 0}

        def _bad_request():
            calls["n"] += 1
            return _FakeResp(400, body={"error": "invalid_grant"})

        resp = _d2l._retry_with_backoff(_bad_request, max_attempts=3,
                                        base_delay=0.0)
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(calls["n"], 1)

    def test_200_immediate_returns(self):
        """200 first try -> immediate return, single call."""
        calls = {"n": 0}

        def _ok():
            calls["n"] += 1
            return _FakeResp(200, body={"ok": True})

        resp = _d2l._retry_with_backoff(_ok, max_attempts=3, base_delay=0.0)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(calls["n"], 1)
