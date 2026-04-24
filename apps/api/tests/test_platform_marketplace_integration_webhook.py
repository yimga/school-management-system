"""Inbound platform integration webhook (HMAC + audit row)."""

from __future__ import annotations

import hashlib
import hmac
import json

from django.test import Client, TestCase
from django.urls import reverse

from apps.platform_runtime.helpers import (
    get_platform_site_settings_record,
    invalidate_effective_site_settings_cache,
)
from apps.platform_runtime.models import PlatformIntegrationWebhookEvent, RuntimeDefaults


class PlatformMarketplaceIntegrationWebhookTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.url = reverse("api:platform-marketplace-integration-webhook")

    def test_returns_503_when_secret_unset(self):
        invalidate_effective_site_settings_cache()
        site = get_platform_site_settings_record(create=True)
        self.assertIsNotNone(site)
        site.apply_feature_control_state(field_updates={"webhook_signing_secret": ""})
        rd = RuntimeDefaults.get_singleton()
        if rd is not None:
            rd.webhook_signing_secret = None
            rd.save(update_fields=["webhook_signing_secret", "updated_at"])
        invalidate_effective_site_settings_cache()
        raw = json.dumps({"event": "ping"}).encode()
        r = self.client.post(
            self.url,
            data=raw,
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 503)
        data = r.json()
        self.assertIn("not configured", data.get("error", ""))

    def test_returns_401_on_bad_signature(self):
        invalidate_effective_site_settings_cache()
        site = get_platform_site_settings_record(create=True)
        self.assertIsNotNone(site)
        site.apply_feature_control_state(
            field_updates={"webhook_signing_secret": "whsec-test-integration-99"}
        )
        invalidate_effective_site_settings_cache()
        raw = json.dumps({"event": "bad"}).encode()
        r = self.client.post(
            self.url,
            data=raw,
            content_type="application/json",
            HTTP_X_RUNMYCAMPUS_INTEGRATION_SIGNATURE="sha256=deadbeef",
        )
        self.assertEqual(r.status_code, 401)
        ev = PlatformIntegrationWebhookEvent.objects.order_by("-id").first()
        self.assertIsNotNone(ev)
        self.assertFalse(ev.verified)
        self.assertEqual(ev.event_type, "bad")

    def test_accepts_valid_hmac_and_records_verified(self):
        invalidate_effective_site_settings_cache()
        site = get_platform_site_settings_record(create=True)
        self.assertIsNotNone(site)
        secret = "whsec-accept-test-aa"
        site.apply_feature_control_state(field_updates={"webhook_signing_secret": secret})
        invalidate_effective_site_settings_cache()
        raw = json.dumps({"type": "inventory.sync"}).encode()
        sig = "sha256=" + hmac.new(secret.encode("utf-8"), raw, hashlib.sha256).hexdigest()
        r = self.client.post(
            self.url,
            data=raw,
            content_type="application/json",
            HTTP_X_RUNMYCAMPUS_INTEGRATION_SIGNATURE=sig,
        )
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json().get("ok"))
        ev = PlatformIntegrationWebhookEvent.objects.order_by("-id").first()
        self.assertIsNotNone(ev)
        self.assertTrue(ev.verified)
        self.assertEqual(ev.event_type, "inventory.sync")
        self.assertEqual(ev.body_sha256, hashlib.sha256(raw).hexdigest())
