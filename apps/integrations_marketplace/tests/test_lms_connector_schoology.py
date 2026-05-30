"""v4.00.92 — Unit tests for ``lms_connector_schoology`` (W11+W15+W21+W22).

Exercises the Schoology OAuth live-path surface end-to-end with
monkeypatched ``requests`` (no live HTTP):

  * ``exchange_authorization_code_for_token`` — dry-run / validation /
    happy-success
  * ``refresh_access_token`` — dry-run / success
  * ``push_grade_live`` — dry-run / 200
  * ``_retry_with_backoff`` — Timeout retry / 4xx no-retry / 200 immediate

Uses ``SimpleTestCase`` — the ``_record_audit`` hook (which would otherwise
write to the ``LMSDiagActionAudit`` model) is stubbed in ``setUp`` so the
tests never touch the DB.
"""

from __future__ import annotations

import os

from django.test import SimpleTestCase

from apps.integrations_marketplace import lms_connector_schoology as _sg


class _FakeResp:
    """Minimal stand-in for ``requests.Response``."""

    def __init__(self, status_code, body=None, headers=None):
        self.status_code = status_code
        self._body = body if body is not None else {}
        self.headers = headers or {}

    def json(self):
        return self._body


class _NoSleep:
    """Drop-in for the ``time`` module that doesn't actually sleep."""

    @staticmethod
    def sleep(_x):
        return None


class _SchoologyTestBase(SimpleTestCase):
    """Shared scaffolding — env capture, audit-hook stub, no-sleep."""

    def setUp(self):
        # Capture / clear the live-outbound env so dry-run vs live is deterministic.
        self._orig_env = os.environ.get(_sg.LIVE_OUTBOUND_ENV)
        # Capture the audit hook so we can swap in a collector.
        self._orig_audit = _sg._record_audit
        self.audit_calls: list[dict] = []

        def _fake_audit(**kw):
            self.audit_calls.append(kw)

        _sg._record_audit = _fake_audit

        # Capture the time module so retry sleeps don't actually pause.
        self._orig_time = _sg._time
        _sg._time = _NoSleep()

        # Capture requests.post / requests.put so monkeypatching is reversible.
        import requests
        self._requests = requests
        self._orig_post = requests.post
        self._orig_put = requests.put

    def tearDown(self):
        if self._orig_env is None:
            os.environ.pop(_sg.LIVE_OUTBOUND_ENV, None)
        else:
            os.environ[_sg.LIVE_OUTBOUND_ENV] = self._orig_env
        _sg._record_audit = self._orig_audit
        _sg._time = self._orig_time
        self._requests.post = self._orig_post
        self._requests.put = self._orig_put

    def _enable_live(self):
        os.environ[_sg.LIVE_OUTBOUND_ENV] = "1"

    def _install_post(self, behavior):
        self._requests.post = behavior

    def _install_put(self, behavior):
        self._requests.put = behavior


class ExchangeAuthorizationCodeTests(_SchoologyTestBase):

    def test_dry_run_when_env_unset(self):
        """No env flag -> dry-run dict w/ reason live_outbound_disabled."""
        # Ensure env is unset.
        os.environ.pop(_sg.LIVE_OUTBOUND_ENV, None)
        result = _sg.exchange_authorization_code_for_token(
            code="abc", client_id="cid", client_secret="cs",
            redirect_uri="https://example.com/cb",
        )
        self.assertTrue(result.get("dry_run"))
        self.assertFalse(result.get("ok"))
        self.assertEqual(result.get("reason"), "live_outbound_disabled_env_unset")
        # No audit row written for dry-run.
        self.assertEqual(self.audit_calls, [])

    def test_validation_error_short_circuits(self):
        """Missing required field -> validation_error + audit row."""
        result = _sg.exchange_authorization_code_for_token(
            code="", client_id="cid", client_secret="cs",
            redirect_uri="https://example.com/cb",
        )
        self.assertEqual(result.get("reason"), "validation_error")
        self.assertFalse(result.get("ok"))
        # One audit call with reason=validation_error.
        self.assertEqual(len(self.audit_calls), 1)
        self.assertEqual(self.audit_calls[0]["reason"], "validation_error")
        self.assertFalse(self.audit_calls[0]["ok"])

    def test_happy_success_via_fake_post(self):
        """Live outbound + 200 JSON body -> ok=True + audit ok=True."""
        self._enable_live()
        fake_body = {
            "access_token": "ya29.fake",
            "refresh_token": "refresh.fake",
            "expires_in": 3600,
            "token_type": "Bearer",
            "scope": "read write",
        }

        def _fake_post(*_args, **_kw):
            return _FakeResp(200, body=fake_body)

        self._install_post(_fake_post)
        result = _sg.exchange_authorization_code_for_token(
            code="auth-code", client_id="cid", client_secret="cs",
            redirect_uri="https://example.com/cb",
            tenant_schema="acme",
        )
        self.assertTrue(result.get("ok"))
        # NEVER assert on raw secret values — verify presence in body keys only.
        self.assertIn("access_token", result)
        self.assertIn("refresh_token", result)
        self.assertIn("issued_at_iso", result)
        # Audit row recorded with ok=True.
        self.assertEqual(len(self.audit_calls), 1)
        self.assertTrue(self.audit_calls[0]["ok"])
        # Verify payload_summary carries hashes, NOT raw tokens.
        ps = self.audit_calls[0].get("payload_summary") or {}
        self.assertNotIn("access_token", ps)
        self.assertNotIn("refresh_token", ps)
        # Hash key present.
        self.assertIn("access_token_hash", ps)


class RefreshAccessTokenTests(_SchoologyTestBase):

    def test_dry_run_when_env_unset(self):
        """Env unset -> dry-run refresh response."""
        os.environ.pop(_sg.LIVE_OUTBOUND_ENV, None)
        result = _sg.refresh_access_token(
            refresh_token="rt", client_id="cid", client_secret="cs",
        )
        self.assertTrue(result.get("dry_run"))
        self.assertEqual(result.get("reason"), "live_outbound_disabled_env_unset")

    def test_happy_refresh_success(self):
        """Live + 200 + rotated refresh-token -> 2 audit rows (rotation + refresh)."""
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
        result = _sg.refresh_access_token(
            refresh_token="old-rt", client_id="cid", client_secret="cs",
            tenant_schema="acme",
        )
        self.assertTrue(result.get("ok"))
        self.assertIn("issued_at_iso", result)
        # W24 H1: rotation audit row + W21 refresh-success audit row.
        actions = [c["action"] for c in self.audit_calls]
        self.assertIn("oauth_refresh", actions)
        self.assertIn("refresh_token_rotation", actions)
        # Both ok=True (refresh succeeded + rotation correctly detected).
        for c in self.audit_calls:
            self.assertTrue(c["ok"])


class PushGradeLiveTests(_SchoologyTestBase):

    def test_dry_run_when_env_unset(self):
        """Env unset -> dry-run shape echoing intended target_url."""
        os.environ.pop(_sg.LIVE_OUTBOUND_ENV, None)
        result = _sg.push_grade_live(
            access_token="at", section_id="sec1", assignment_id="a1",
            student_id="u1", score=85.0, max_score=100.0,
        )
        self.assertTrue(result.get("dry_run"))
        self.assertEqual(result.get("reason"), "live_outbound_disabled_env_unset")
        self.assertIn("sec1/grades", result.get("target_url", ""))

    def test_happy_200_returns_ok(self):
        """Live + 200 PUT -> ok=True + audit ok=True."""
        self._enable_live()

        def _fake_put(*_args, **_kw):
            return _FakeResp(200, body={"ok": True})

        self._install_put(_fake_put)
        result = _sg.push_grade_live(
            access_token="at", section_id="sec1", assignment_id="a1",
            student_id="u1", score=85.0, max_score=100.0,
            tenant_schema="acme",
        )
        self.assertTrue(result.get("ok"))
        self.assertEqual(result.get("http_status"), 200)
        self.assertEqual(len(self.audit_calls), 1)
        self.assertEqual(self.audit_calls[0]["action"], "push_grade_live")


class RetryWithBackoffTests(_SchoologyTestBase):

    def test_timeout_then_success_retries(self):
        """Timeout once, then 200 -> succeed on attempt 2 (no exception)."""
        import requests
        calls = {"n": 0}

        def _flaky():
            calls["n"] += 1
            if calls["n"] == 1:
                raise requests.Timeout("simulated timeout")
            return _FakeResp(200, body={"ok": True})

        resp = _sg._retry_with_backoff(_flaky, max_attempts=3, base_delay=0.0)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(calls["n"], 2)

    def test_4xx_does_not_retry(self):
        """4xx returns immediately on first attempt (no retry)."""
        calls = {"n": 0}

        def _bad_request():
            calls["n"] += 1
            return _FakeResp(400, body={"error": "invalid_grant"})

        resp = _sg._retry_with_backoff(_bad_request, max_attempts=3,
                                       base_delay=0.0)
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(calls["n"], 1)

    def test_200_immediate_returns(self):
        """200 on first attempt returns immediately, no retries."""
        calls = {"n": 0}

        def _ok():
            calls["n"] += 1
            return _FakeResp(200, body={"ok": True})

        resp = _sg._retry_with_backoff(_ok, max_attempts=3, base_delay=0.0)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(calls["n"], 1)
