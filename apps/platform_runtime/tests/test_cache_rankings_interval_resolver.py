"""Siteconfig decomposition slice: cache_rankings_interval_minutes via RuntimeDefaults."""

from django.test import TestCase

from apps.platform_runtime.helpers import get_effective_site_settings
from apps.platform_runtime.models import RuntimeDefaults
from apps.platform_runtime.tests.support.runtime_defaults_first_class import (
    assert_effective_settings_use_runtime_column_over_legacy_site,
)


class CacheRankingsIntervalResolverTests(TestCase):
    def test_runtime_defaults_column_surfaces_on_effective_settings(self):
        rd = RuntimeDefaults.get_singleton()
        rd.cache_rankings_interval_minutes = 42
        rd.save(update_fields=["cache_rankings_interval_minutes"])

        eff = get_effective_site_settings(request=None, school=None)
        self.assertEqual(getattr(eff, "cache_rankings_interval_minutes", None), 42)

    def test_runtime_column_wins_over_legacy_payload_snapshot(self):
        assert_effective_settings_use_runtime_column_over_legacy_site(
            self,
            "cache_rankings_interval_minutes",
            legacy_site_value=99,
            runtime_column_value=15,
        )
