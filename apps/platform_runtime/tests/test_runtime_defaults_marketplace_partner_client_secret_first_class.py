"""Batch 14+ marketplace_integrations: marketplace_partner_client_secret as RuntimeDefaults column."""

from __future__ import annotations

from django.test import TestCase

from apps.platform_runtime.helpers import (
    get_effective_site_settings,
    get_platform_site_settings_record,
    invalidate_effective_site_settings_cache,
)
from apps.platform_runtime.models import RuntimeDefaults


class RuntimeDefaultsMarketplacePartnerClientSecretFirstClassTests(TestCase):
    def test_site_save_sync_writes_column_not_payload(self):
        site = get_platform_site_settings_record(create=True)
        self.assertIsNotNone(site)
        site.marketplace_partner_client_secret = "mkt-partner-sync-test"
        site.save()
        rd = RuntimeDefaults.get_singleton()
        self.assertIsNotNone(rd)
        self.assertEqual(rd.marketplace_partner_client_secret, "mkt-partner-sync-test")
        self.assertNotIn("marketplace_partner_client_secret", rd.payload or {})

    def test_effective_settings_uses_runtime_column_over_legacy_site(self):
        invalidate_effective_site_settings_cache()
        site = get_platform_site_settings_record(create=True)
        self.assertIsNotNone(site)
        site.marketplace_partner_client_secret = "from-legacy-site-row"
        site.save()
        rd = RuntimeDefaults.get_singleton()
        self.assertIsNotNone(rd)
        rd.marketplace_partner_client_secret = "from-runtime-column"
        pl = dict(rd.payload or {})
        pl.pop("marketplace_partner_client_secret", None)
        rd.payload = pl
        rd.save(
            update_fields=[
                "marketplace_partner_client_secret",
                "payload",
                "updated_at",
            ]
        )
        invalidate_effective_site_settings_cache()
        eff = get_effective_site_settings(request=None, school=None)
        self.assertIsNotNone(eff)
        self.assertEqual(
            getattr(eff, "marketplace_partner_client_secret", None),
            "from-runtime-column",
        )

    def test_sync_strips_marketplace_partner_client_secret_from_runtime_payload(self):
        site = get_platform_site_settings_record(create=True)
        self.assertIsNotNone(site)
        site.marketplace_partner_client_secret = "k-partner"
        site.save()
        rd = RuntimeDefaults.get_singleton()
        self.assertIsNotNone(rd)
        pl = dict(rd.payload or {})
        pl["marketplace_partner_client_secret"] = "should-not-persist-in-payload"
        rd.payload = pl
        rd.save(update_fields=["payload", "updated_at"])
        RuntimeDefaults.sync_from_site_settings(site)
        rd.refresh_from_db()
        self.assertEqual(rd.marketplace_partner_client_secret, "k-partner")
        self.assertNotIn("marketplace_partner_client_secret", rd.payload or {})
