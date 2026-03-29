"""Batch 14+ marketplace_integrations: smtp_password as RuntimeDefaults first-class column."""

from __future__ import annotations

from django.test import TestCase

from apps.platform_runtime.helpers import (
    get_effective_site_settings,
    get_platform_site_settings_record,
    invalidate_effective_site_settings_cache,
)
from apps.platform_runtime.models import RuntimeDefaults


class RuntimeDefaultsSmtpPasswordFirstClassTests(TestCase):
    def test_site_save_sync_writes_column_not_payload(self):
        site = get_platform_site_settings_record(create=True)
        self.assertIsNotNone(site)
        site.smtp_password = "smtp-synced-secret-xyz"
        site.save()
        rd = RuntimeDefaults.get_singleton()
        self.assertIsNotNone(rd)
        self.assertEqual(rd.smtp_password, "smtp-synced-secret-xyz")
        self.assertNotIn("smtp_password", rd.payload or {})

    def test_effective_settings_uses_runtime_column_over_legacy_site(self):
        invalidate_effective_site_settings_cache()
        site = get_platform_site_settings_record(create=True)
        self.assertIsNotNone(site)
        site.smtp_password = "from-legacy-site-row"
        site.save()
        rd = RuntimeDefaults.get_singleton()
        self.assertIsNotNone(rd)
        rd.smtp_password = "from-runtime-column"
        pl = dict(rd.payload or {})
        pl.pop("smtp_password", None)
        rd.payload = pl
        rd.save(update_fields=["smtp_password", "payload", "updated_at"])
        invalidate_effective_site_settings_cache()
        eff = get_effective_site_settings(request=None, school=None)
        self.assertIsNotNone(eff)
        self.assertEqual(getattr(eff, "smtp_password", None), "from-runtime-column")

    def test_sync_strips_smtp_password_from_runtime_payload(self):
        site = get_platform_site_settings_record(create=True)
        self.assertIsNotNone(site)
        site.smtp_password = "k-smtp"
        site.save()
        rd = RuntimeDefaults.get_singleton()
        self.assertIsNotNone(rd)
        pl = dict(rd.payload or {})
        pl["smtp_password"] = "should-not-persist-in-payload"
        rd.payload = pl
        rd.save(update_fields=["payload", "updated_at"])
        RuntimeDefaults.sync_from_site_settings(site)
        rd.refresh_from_db()
        self.assertEqual(rd.smtp_password, "k-smtp")
        self.assertNotIn("smtp_password", rd.payload or {})
