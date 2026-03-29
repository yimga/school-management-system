"""Batch 14+ marketplace_integrations: ai_provider_api_key as RuntimeDefaults first-class column."""

from __future__ import annotations

from django.test import TestCase

from apps.platform_runtime.helpers import (
    get_effective_site_settings,
    get_platform_site_settings_record,
    invalidate_effective_site_settings_cache,
)
from apps.platform_runtime.models import RuntimeDefaults


class RuntimeDefaultsAiProviderApiKeyFirstClassTests(TestCase):
    def test_site_save_sync_writes_column_not_payload(self):
        site = get_platform_site_settings_record(create=True)
        self.assertIsNotNone(site)
        site.ai_provider_api_key = "ai-synced-key-xyz"
        site.save()
        rd = RuntimeDefaults.get_singleton()
        self.assertIsNotNone(rd)
        self.assertEqual(rd.ai_provider_api_key, "ai-synced-key-xyz")
        self.assertNotIn("ai_provider_api_key", rd.payload or {})

    def test_effective_settings_uses_runtime_column_over_legacy_site(self):
        invalidate_effective_site_settings_cache()
        site = get_platform_site_settings_record(create=True)
        self.assertIsNotNone(site)
        site.ai_provider_api_key = "from-legacy-site-row"
        site.save()
        rd = RuntimeDefaults.get_singleton()
        self.assertIsNotNone(rd)
        rd.ai_provider_api_key = "from-runtime-column"
        pl = dict(rd.payload or {})
        pl.pop("ai_provider_api_key", None)
        rd.payload = pl
        rd.save(update_fields=["ai_provider_api_key", "payload", "updated_at"])
        invalidate_effective_site_settings_cache()
        eff = get_effective_site_settings(request=None, school=None)
        self.assertIsNotNone(eff)
        self.assertEqual(getattr(eff, "ai_provider_api_key", None), "from-runtime-column")

    def test_sync_strips_ai_provider_api_key_from_runtime_payload(self):
        site = get_platform_site_settings_record(create=True)
        self.assertIsNotNone(site)
        site.ai_provider_api_key = "k-ai"
        site.save()
        rd = RuntimeDefaults.get_singleton()
        self.assertIsNotNone(rd)
        pl = dict(rd.payload or {})
        pl["ai_provider_api_key"] = "should-not-persist-in-payload"
        rd.payload = pl
        rd.save(update_fields=["payload", "updated_at"])
        RuntimeDefaults.sync_from_site_settings(site)
        rd.refresh_from_db()
        self.assertEqual(rd.ai_provider_api_key, "k-ai")
        self.assertNotIn("ai_provider_api_key", rd.payload or {})
