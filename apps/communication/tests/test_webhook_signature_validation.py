"""Tests for WhatsApp + Zoom webhook signature validation (Surface 1.4)."""

from __future__ import annotations

import hashlib
import hmac
import time

from django.test import SimpleTestCase, override_settings


class _FakeRequest:
    """Minimal request stub: method + body + headers + GET."""

    def __init__(self, method="POST", body=b"", headers=None, get=None, meta=None):
        self.method = method
        self.body = body
        self.headers = headers or {}
        self.GET = get or {}
        self.META = meta or {}


@override_settings(
    WHATSAPP_API_TOKEN="t",
    WHATSAPP_API_URL="https://example.test",
    WHATSAPP_BUSINESS_NUMBER="+10000000000",
    WHATSAPP_VERIFY_TOKEN="vtok-unit",
    WHATSAPP_APP_SECRET="appsecret-unit",
)
class WhatsAppVerifyWebhookTests(SimpleTestCase):
    def _integration(self):
        from apps.communication.integrations import WhatsAppIntegration

        return WhatsAppIntegration()

    def test_get_handshake_with_correct_token_passes(self):
        wa = self._integration()
        req = _FakeRequest(
            method="GET",
            get={"hub.mode": "subscribe", "hub.verify_token": "vtok-unit"},
        )
        self.assertTrue(wa.verify_webhook(req))

    def test_get_handshake_with_wrong_token_fails(self):
        wa = self._integration()
        req = _FakeRequest(
            method="GET",
            get={"hub.mode": "subscribe", "hub.verify_token": "WRONG"},
        )
        self.assertFalse(wa.verify_webhook(req))

    def test_get_handshake_wrong_mode_fails(self):
        wa = self._integration()
        req = _FakeRequest(
            method="GET",
            get={"hub.mode": "unsubscribe", "hub.verify_token": "vtok-unit"},
        )
        self.assertFalse(wa.verify_webhook(req))

    def test_post_with_valid_signature_passes(self):
        wa = self._integration()
        body = b'{"entry":[{"id":"1"}]}'
        sig = hmac.new(b"appsecret-unit", body, hashlib.sha256).hexdigest()
        req = _FakeRequest(
            method="POST",
            body=body,
            headers={"X-Hub-Signature-256": f"sha256={sig}"},
        )
        self.assertTrue(wa.verify_webhook(req))

    def test_post_with_invalid_signature_fails(self):
        wa = self._integration()
        body = b'{"entry":[{"id":"1"}]}'
        req = _FakeRequest(
            method="POST",
            body=body,
            headers={"X-Hub-Signature-256": "sha256=deadbeef"},
        )
        self.assertFalse(wa.verify_webhook(req))

    def test_post_missing_signature_fails(self):
        wa = self._integration()
        req = _FakeRequest(method="POST", body=b'{}', headers={})
        self.assertFalse(wa.verify_webhook(req))


@override_settings(
    ZOOM_API_KEY="k",
    ZOOM_API_SECRET="s",
    ZOOM_WEBHOOK_SECRET_TOKEN="zoom-secret-unit",
)
class ZoomVerifyWebhookTests(SimpleTestCase):
    def _integration(self):
        from apps.communication.integrations import ZoomIntegration

        return ZoomIntegration()

    def test_valid_signature_passes(self):
        zoom = self._integration()
        body = b'{"event":"meeting.started"}'
        ts = str(int(time.time()))
        msg = f"v0:{ts}:".encode() + body
        digest = hmac.new(b"zoom-secret-unit", msg, hashlib.sha256).hexdigest()
        req = _FakeRequest(
            method="POST",
            body=body,
            headers={
                "x-zm-signature": f"v0={digest}",
                "x-zm-request-timestamp": ts,
            },
        )
        self.assertTrue(zoom.verify_webhook(req))

    def test_skewed_timestamp_rejected(self):
        zoom = self._integration()
        body = b"{}"
        ts = str(int(time.time()) - 1000)
        msg = f"v0:{ts}:".encode() + body
        digest = hmac.new(b"zoom-secret-unit", msg, hashlib.sha256).hexdigest()
        req = _FakeRequest(
            method="POST",
            body=body,
            headers={
                "x-zm-signature": f"v0={digest}",
                "x-zm-request-timestamp": ts,
            },
        )
        self.assertFalse(zoom.verify_webhook(req))

    def test_missing_signature_rejected(self):
        zoom = self._integration()
        req = _FakeRequest(method="POST", body=b"{}", headers={})
        self.assertFalse(zoom.verify_webhook(req))

    def test_wrong_secret_rejected(self):
        zoom = self._integration()
        body = b"{}"
        ts = str(int(time.time()))
        # Sign with a different secret
        msg = f"v0:{ts}:".encode() + body
        digest = hmac.new(b"WRONG", msg, hashlib.sha256).hexdigest()
        req = _FakeRequest(
            method="POST",
            body=body,
            headers={
                "x-zm-signature": f"v0={digest}",
                "x-zm-request-timestamp": ts,
            },
        )
        self.assertFalse(zoom.verify_webhook(req))


