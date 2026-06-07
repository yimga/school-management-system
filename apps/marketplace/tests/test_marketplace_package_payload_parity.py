"""PackageVersion payloads exist for every marketplace catalog slug."""

from django.core.management import call_command
from django.test import TestCase

from apps.marketplace.management.commands.seed_marketplace_apps import FIRST_PARTY_APPS
from apps.marketplace.marketplace_package_payloads import (
    build_marketplace_package_payload,
    catalog_app_package_rows,
    resolve_package_id_for_app,
)
from apps.packages.models import PackageVersion


class MarketplacePackagePayloadTests(TestCase):
    def test_build_payload_always_non_empty(self):
        for app_def in FIRST_PARTY_APPS:
            slug = app_def["slug"]
            payload = build_marketplace_package_payload(
                slug=slug,
                name=app_def.get("name") or slug,
                version=app_def.get("version") or "1.0",
                manifest=app_def.get("manifest") or {},
                description=app_def.get("description") or "",
            )
            self.assertTrue(payload, msg=slug)
            section = next(iter(payload.values()))
            self.assertEqual(section.get("app_slug"), slug, msg=slug)

    def test_seed_command_creates_all_catalog_packages(self):
        call_command("seed_marketplace_catalog_packages", verbosity=0)
        for app_def in FIRST_PARTY_APPS:
            slug = app_def["slug"]
            pid = resolve_package_id_for_app(slug, app_def.get("manifest") or {})
            ver = str(app_def.get("version") or "1.0")
            pv = PackageVersion.objects.filter(package_id=pid, version=ver).first()
            self.assertIsNotNone(pv, msg=f"{slug} -> {pid}")
            self.assertTrue(pv.payload_sections, msg=slug)

    def test_catalog_rows_count_matches_apps(self):
        rows = catalog_app_package_rows(FIRST_PARTY_APPS)
        self.assertEqual(len(rows), len(FIRST_PARTY_APPS))
