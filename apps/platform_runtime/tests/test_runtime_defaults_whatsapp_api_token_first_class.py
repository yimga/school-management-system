"""Batch 14+ marketplace_integrations: whatsapp_api_token as RuntimeDefaults first-class column."""

from __future__ import annotations

from django.test import TestCase

from apps.platform_runtime.tests.support.runtime_defaults_first_class import (
    assert_effective_settings_use_runtime_column_over_legacy_site,
    assert_site_save_sync_writes_column_not_payload,
    assert_sync_strips_field_from_runtime_payload,
)


class RuntimeDefaultsWhatsappApiTokenFirstClassTests(TestCase):
    _FIELD = "whatsapp_api_token"

    def test_site_save_sync_writes_column_not_payload(self):
        assert_site_save_sync_writes_column_not_payload(
            self,
            self._FIELD,
            sync_value="wa-synced-token-xyz",
        )

    def test_effective_settings_uses_runtime_column_over_legacy_site(self):
        assert_effective_settings_use_runtime_column_over_legacy_site(
            self,
            self._FIELD,
            legacy_site_value="from-legacy-site-row",
            runtime_column_value="from-runtime-column",
        )

    def test_sync_strips_whatsapp_api_token_from_runtime_payload(self):
        assert_sync_strips_field_from_runtime_payload(
            self,
            self._FIELD,
            canonical_value="k-wa",
            shadow_payload_value="should-not-persist-in-payload",
        )
