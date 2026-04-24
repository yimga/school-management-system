"""Batch 14+ marketplace_integrations: marketplace_partner_client_secret as RuntimeDefaults column."""

from __future__ import annotations

from django.test import TestCase

from apps.platform_runtime.tests.support.runtime_defaults_first_class import (
    assert_effective_settings_use_runtime_column_over_legacy_site,
    assert_site_save_sync_writes_column_not_payload,
    assert_sync_strips_field_from_runtime_payload,
)


class RuntimeDefaultsMarketplacePartnerClientSecretFirstClassTests(TestCase):
    _FIELD = "marketplace_partner_client_secret"

    def test_site_save_sync_writes_column_not_payload(self):
        assert_site_save_sync_writes_column_not_payload(
            self,
            self._FIELD,
            sync_value="mkt-partner-sync-test",
        )

    def test_effective_settings_uses_runtime_column_over_legacy_site(self):
        assert_effective_settings_use_runtime_column_over_legacy_site(
            self,
            self._FIELD,
            legacy_site_value="from-legacy-site-row",
            runtime_column_value="from-runtime-column",
        )

    def test_sync_strips_marketplace_partner_client_secret_from_runtime_payload(self):
        assert_sync_strips_field_from_runtime_payload(
            self,
            self._FIELD,
            canonical_value="k-partner",
            shadow_payload_value="should-not-persist-in-payload",
        )
