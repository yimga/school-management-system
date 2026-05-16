"""Tests for `apps.integrations_marketplace.webhooks` (v2.79).

HMAC signature verification (default + Slack-specific scheme), replay-window
enforcement, and the handler-registry dispatch contract.
"""

from __future__ import annotations

import hashlib
import hmac
import time
from unittest import mock

from django.test import RequestFactory, SimpleTestCase

from apps.integrations_marketplace import webhooks
from apps.integrations_marketplace.webhooks import (
    SIGNATURE_WINDOW_SECONDS,
    WEBHOOK_HANDLERS,
    _expected_signature,
    _verify_default_signature,
    _verify_slack_signature,
    register_webhook_handler,
)


class _FakeRow:
    """Minimal ServiceIntegration stand-in carrying just what verifiers read."""

    def __init__(self, *, slug="slack", secret="topsecret"):
        self.connector_slug = slug
        self.config = {"webhook_secret": secret}
        self.is_active = True
        self.pk = 1


class DefaultSignatureVerifierTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.secret = "shhh"

    def _sign_and_request(self, body: bytes, timestamp: int) -> mock.Mock:
        sig = _expected_signature(
            secret=self.secret, timestamp=str(timestamp), body=body
        )
        req = self.factory.post("/integrations/webhook/x/1/", data=body,
                                content_type="application/json")
        # Stamp the headers dict that the verifier reads.
        req.META["HTTP_X_RMC_SIGNATURE"] = f"v0={sig}"
        req.META["HTTP_X_RMC_TIMESTAMP"] = str(timestamp)
        return req

    def test_valid_signature_passes(self):
        ts = int(time.time())
        req = self._sign_and_request(b'{"k":"v"}', ts)
        ok, reason = _verify_default_signature(request=req, secret=self.secret)
        self.assertTrue(ok, reason)

    def test_missing_headers_fails(self):
        req = self.factory.post("/integrations/webhook/x/1/", data=b"{}",
                                content_type="application/json")
        ok, reason = _verify_default_signature(request=req, secret=self.secret)
        self.assertFalse(ok)
        self.assertEqual(reason, "missing_signature_or_timestamp")

    def test_outside_replay_window_fails(self):
        ts = int(time.time()) - SIGNATURE_WINDOW_SECONDS - 30
        req = self._sign_and_request(b"{}", ts)
        ok, reason = _verify_default_signature(request=req, secret=self.secret)
        self.assertFalse(ok)
        self.assertEqual(reason, "timestamp_outside_window")

    def test_bad_timestamp_fails(self):
        req = self.factory.post("/integrations/webhook/x/1/", data=b"{}",
                                content_type="application/json")
        req.META["HTTP_X_RMC_SIGNATURE"] = "v0=abc"
        req.META["HTTP_X_RMC_TIMESTAMP"] = "not-a-number"
        ok, reason = _verify_default_signature(request=req, secret=self.secret)
        self.assertFalse(ok)
        self.assertEqual(reason, "bad_timestamp")

    def test_unknown_signature_format_fails(self):
        ts = int(time.time())
        req = self.factory.post("/integrations/webhook/x/1/", data=b"{}",
                                content_type="application/json")
        req.META["HTTP_X_RMC_SIGNATURE"] = "sha256=deadbeef"  # not v0=
        req.META["HTTP_X_RMC_TIMESTAMP"] = str(ts)
        ok, reason = _verify_default_signature(request=req, secret=self.secret)
        self.assertFalse(ok)
        self.assertEqual(reason, "unknown_signature_format")

    def test_signature_mismatch_fails(self):
        ts = int(time.time())
        req = self.factory.post("/integrations/webhook/x/1/", data=b'{"a":1}',
                                content_type="application/json")
        req.META["HTTP_X_RMC_SIGNATURE"] = "v0=" + ("0" * 64)
        req.META["HTTP_X_RMC_TIMESTAMP"] = str(ts)
        ok, reason = _verify_default_signature(request=req, secret=self.secret)
        self.assertFalse(ok)
        self.assertEqual(reason, "signature_mismatch")

    def test_body_tampering_after_signing_fails(self):
        ts = int(time.time())
        req = self._sign_and_request(b'{"orig":1}', ts)
        # Substitute the body but keep the original signature → must fail.
        req._body = b'{"tampered":1}'
        ok, reason = _verify_default_signature(request=req, secret=self.secret)
        self.assertFalse(ok)
        self.assertEqual(reason, "signature_mismatch")


class SlackSignatureVerifierTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.secret = "slack-signing-secret"

    def _slack_signed(self, body: bytes, timestamp: int) -> mock.Mock:
        base = f"v0:{timestamp}:".encode("utf-8") + body
        sig = "v0=" + hmac.new(
            self.secret.encode("utf-8"), base, hashlib.sha256
        ).hexdigest()
        req = self.factory.post("/integrations/webhook/slack/1/", data=body,
                                content_type="application/json")
        req.META["HTTP_X_SLACK_SIGNATURE"] = sig
        req.META["HTTP_X_SLACK_REQUEST_TIMESTAMP"] = str(timestamp)
        return req

    def test_valid_slack_signature_passes(self):
        ts = int(time.time())
        req = self._slack_signed(b'{"event":"x"}', ts)
        ok, reason = _verify_slack_signature(request=req, secret=self.secret)
        self.assertTrue(ok, reason)

    def test_missing_slack_headers_fails(self):
        req = self.factory.post("/integrations/webhook/slack/1/", data=b"{}",
                                content_type="application/json")
        ok, reason = _verify_slack_signature(request=req, secret=self.secret)
        self.assertFalse(ok)
        self.assertEqual(reason, "missing_slack_headers")

    def test_slack_replay_window_enforced(self):
        ts = int(time.time()) - SIGNATURE_WINDOW_SECONDS - 1
        req = self._slack_signed(b"{}", ts)
        ok, reason = _verify_slack_signature(request=req, secret=self.secret)
        self.assertFalse(ok)
        self.assertEqual(reason, "slack_timestamp_outside_window")

    def test_slack_signature_uses_v0_colon_scheme_not_rmc_scheme(self):
        # Mix-up: stamp an RMC-style signature on a Slack-bound request → fails.
        ts = int(time.time())
        rmc_sig = _expected_signature(secret=self.secret, timestamp=str(ts), body=b"{}")
        req = self.factory.post("/integrations/webhook/slack/1/", data=b"{}",
                                content_type="application/json")
        req.META["HTTP_X_SLACK_SIGNATURE"] = f"v0={rmc_sig}"
        req.META["HTTP_X_SLACK_REQUEST_TIMESTAMP"] = str(ts)
        ok, reason = _verify_slack_signature(request=req, secret=self.secret)
        self.assertFalse(ok)
        self.assertEqual(reason, "slack_signature_mismatch")


class HandlerRegistryTests(SimpleTestCase):
    def tearDown(self):
        # Don't leak test handlers into other test files.
        WEBHOOK_HANDLERS.pop("__test_slug__", None)

    def test_decorator_registers_handler_under_lowercase_slug(self):
        @register_webhook_handler("__TEST_SLUG__")
        def _h(row, payload):
            return None

        self.assertIn("__test_slug__", WEBHOOK_HANDLERS)
        self.assertIs(WEBHOOK_HANDLERS["__test_slug__"], _h)


class WebhookViewIntegrationTests(SimpleTestCase):
    """Verify the view's `_verify` shim picks the right verifier per slug."""

    def test_verify_routes_slack_to_slack_verifier(self):
        row = _FakeRow(slug="slack", secret="s")
        req = mock.Mock(headers={}, body=b"{}", META={})
        slack_call = mock.Mock(return_value=(True, "ok"))
        default_call = mock.Mock()
        # `_SPECIAL_VERIFIERS` was built at import time with the original
        # function reference, so patching `_verify_slack_signature` on the
        # module wouldn't dislodge it — patch the dict entry instead.
        with mock.patch.dict(webhooks._SPECIAL_VERIFIERS,
                             {"slack": slack_call}, clear=False), \
             mock.patch.object(webhooks, "_verify_default_signature", default_call):
            ok, _reason = webhooks._verify(request=req, row=row)
        self.assertTrue(ok)
        slack_call.assert_called_once()
        default_call.assert_not_called()

    def test_verify_routes_non_slack_to_default_verifier(self):
        row = _FakeRow(slug="zoom", secret="s")
        req = mock.Mock(headers={}, body=b"{}", META={})
        slack_call = mock.Mock()
        default_call = mock.Mock(return_value=(True, "ok"))
        with mock.patch.dict(webhooks._SPECIAL_VERIFIERS,
                             {"slack": slack_call}, clear=False), \
             mock.patch.object(webhooks, "_verify_default_signature", default_call):
            ok, _reason = webhooks._verify(request=req, row=row)
        self.assertTrue(ok)
        slack_call.assert_not_called()
        default_call.assert_called_once()

    def test_verify_refuses_when_no_webhook_secret_configured(self):
        row = _FakeRow(slug="zoom", secret="")
        req = mock.Mock(headers={}, body=b"{}", META={})
        ok, reason = webhooks._verify(request=req, row=row)
        self.assertFalse(ok)
        self.assertEqual(reason, "no_webhook_secret_configured")
