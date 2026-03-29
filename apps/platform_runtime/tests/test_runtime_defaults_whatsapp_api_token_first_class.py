"""Batch 14+ marketplace_integrations: whatsapp_api_token as RuntimeDefaults first-class column."""

from __future__ import annotations

from django.test import TestCase

from apps.platform_runtime.helpers import (
    get_effective_site_settings,
    get_platform_site_settings_record,
    invalidate_effective_site_settings_cache,
)
from apps.platform_runtime.models import RuntimeDefaults


class RuntimeDefaultsWhatsappApiTokenFirstClassTests(TestCase):
    def test_site_save_sync_writes_column_not_payload(self):
        site = get_platform_site_settings_record(create=True)
        self.assertIsNotNone(site)
        site.whatsapp_api_token = "wa-synced-token-xyz"
        site.save()
        rd = RuntimeDefaults.get_singleton()
        self.assertIsNotNone(rd)
        self.assertEqual(rd.whatsapp_api_token, "wa-synced-token-xyz")
        self.assertNotIn("whatsapp_api_token", rd.payload or {})

    def test_effective_settings_uses_runtime_column_over_legacy_site(self):
        invalidate_effective_site_settings_cache()
        site = get_platform_site_settings_record(create=True)
        self.assertIsNotNone(site)
        site.whatsapp_api_token = "from-legacy-site-row"
        site.save()
        rd = RuntimeDefaults.get_singleton()
        self.assertIsNotNone(rd)
        rd.whatsapp_api_token = "from-runtime-column"
        pl = dict(rd.payload or {})
        pl.pop("whatsapp_api_token", None)
        rd.payload = pl
        rd.save(update_fields=["whatsapp_api_token", "payload", "updated_at"])
        invalidate_effective_site_settings_cache()
        eff = get_effective_site_settings(request=None, school=None)
        self.assertIsNotNone(eff)
        self.assertEqual(getattr(eff, "whatsapp_api_token", None), "from-runtime-column")

    def test_sync_strips_whatsapp_api_token_from_runtime_payload(self):
        site = get_platform_site_settings_record(create=True)
        self.assertIsNotNone(site)
        site.whatsapp_api_token = "k-wa"
        site.save()
        rd = RuntimeDefaults.get_singleton()
        self.assertIsNotNone(rd)
        pl = dict(rd.payload or {})
        pl["whatsapp_api_token"] = "should-not-persist-in-payload"
        rd.payload = pl
        rd.save(update_fields=["payload", "updated_at"])
        RuntimeDefaults.sync_from_site_settings(site)
        rd.refresh_from_db()
        self.assertEqual(rd.whatsapp_api_token, "k-wa")
        self.assertNotIn("whatsapp_api_token", rd.payload or {})
