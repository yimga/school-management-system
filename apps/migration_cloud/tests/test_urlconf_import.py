"""Ensure migration_cloud models and routes load through full ROOT_URLCONF."""

from __future__ import annotations

from django.test import SimpleTestCase
from django.urls import NoReverseMatch, reverse

from apps.migration_cloud.models import AssetStatus


class MigrationCloudUrlconfImportTests(SimpleTestCase):
    def test_asset_status_enum_importable(self) -> None:
        self.assertTrue(AssetStatus.PENDING)
        self.assertGreaterEqual(len(AssetStatus.choices), 3)

    def test_super_console_route_resolves_via_config_urls(self) -> None:
        path = reverse("migration_cloud_super:console", urlconf="config.urls")
        self.assertTrue(path.endswith("/super/migration/") or "/super/migration/" in path)

    def test_portal_console_route_resolves_via_config_urls(self) -> None:
        try:
            reverse("migration_cloud_portal:console", urlconf="config.urls")
        except NoReverseMatch as exc:
            self.fail(f"migration_cloud_portal:console must resolve in config.urls: {exc}")
