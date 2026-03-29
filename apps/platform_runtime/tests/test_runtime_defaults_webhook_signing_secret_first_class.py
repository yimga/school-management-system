"""Batch 14+ marketplace_integrations: webhook_signing_secret as RuntimeDefaults first-class column."""

from __future__ import annotations

from django.test import TestCase

from apps.platform_runtime.helpers import (
    get_effective_site_settings,
    get_platform_site_settings_record,
    invalidate_effective_site_settings_cache,
)
from apps.platform_runtime.models import RuntimeDefaults


class RuntimeDefaultsWebhookSigningSecretFirstClassTests(TestCase):
    def test_site_save_sync_writes_column_not_payload(self):
        site = get_platform_site_settings_record(create=True)
        self.assertIsNotNone(site)
        site.webhook_signing_secret = "whsec-synced-test-abc"
        site.save()
        rd = RuntimeDefaults.get_singleton()
        self.assertIsNotNone(rd)
        self.assertEqual(rd.webhook_signing_secret, "whsec-synced-test-abc")
        self.assertNotIn("webhook_signing_secret", rd.payload or {})

    def test_effective_settings_uses_runtime_column_over_legacy_site(self):
        invalidate_effective_site_settings_cache()
        site = get_platform_site_settings_record(create=True)
        self.assertIsNotNone(site)
        site.webhook_signing_secret = "from-legacy-site-row"
        site.save()
        rd = RuntimeDefaults.get_singleton()
        self.assertIsNotNone(rd)
        rd.webhook_signing_secret = "from-runtime-column"
        pl = dict(rd.payload or {})
        pl.pop("webhook_signing_secret", None)
        rd.payload = pl
        rd.save(update_fields=["webhook_signing_secret", "payload", "updated_at"])
        invalidate_effective_site_settings_cache()
        eff = get_effective_site_settings(request=None, school=None)
        self.assertIsNotNone(eff)
        self.assertEqual(
            getattr(eff, "webhook_signing_secret", None), "from-runtime-column"
        )

    def test_sync_strips_webhook_signing_secret_from_runtime_payload(self):
        site = get_platform_site_settings_record(create=True)
        self.assertIsNotNone(site)
        site.webhook_signing_secret = "k-webhook"
        site.save()
        rd = RuntimeDefaults.get_singleton()
        self.assertIsNotNone(rd)
        pl = dict(rd.payload or {})
        pl["webhook_signing_secret"] = "should-not-persist-in-payload"
        rd.payload = pl
        rd.save(update_fields=["payload", "updated_at"])
        RuntimeDefaults.sync_from_site_settings(site)
        rd.refresh_from_db()
        self.assertEqual(rd.webhook_signing_secret, "k-webhook")
        self.assertNotIn("webhook_signing_secret", rd.payload or {})
