"""Platform /admin/ catalog builder — section grouping and super bridge URLs."""

from django.test import SimpleTestCase
from django.urls import reverse

from apps.siteconfig.platform_admin_catalog import (
    build_platform_admin_catalog,
    enrich_app_index_models,
)


class PlatformAdminCatalogTests(SimpleTestCase):
    def test_empty_app_list_returns_zero_counts(self):
        catalog = build_platform_admin_catalog([])
        self.assertEqual(catalog["model_count"], 0)
        self.assertEqual(catalog["app_count"], 0)
        self.assertEqual(catalog["sections"], [])

    def test_groups_models_by_section_and_skips_hidden(self):
        app_list = [
            {
                "app_label": "siteconfig",
                "name": "Siteconfig",
                "section": "Platform Configuration",
                "models": [
                    {
                        "name": "Site settings",
                        "object_name": "SiteSettings",
                        "admin_url": "/admin/siteconfig/sitesettings/",
                        "add_url": "/admin/siteconfig/sitesettings/add/",
                    },
                    {"name": "Hidden", "object_name": "Hidden", "hidden": True},
                ],
            },
            {
                "app_label": "billing",
                "name": "Billing",
                "section": "Advanced System Objects",
                "models": [
                    {
                        "name": "Waiver",
                        "object_name": "WaiverRequest",
                        "admin_url": "/admin/billing/waiverrequest/",
                    },
                ],
            },
        ]
        catalog = build_platform_admin_catalog(app_list)
        self.assertEqual(catalog["model_count"], 2)
        self.assertEqual(catalog["app_count"], 2)
        titles = [s["title"] for s in catalog["sections"]]
        self.assertEqual(titles[0], "Platform Configuration")
        self.assertIn("Advanced System Objects", titles)
        site_row = catalog["sections"][0]["apps"][0]["models"][0]
        self.assertIn("site settings", site_row["search_blob"])
        self.assertEqual(site_row["admin_url"], "/admin/siteconfig/sitesettings/")

    def test_bridge_admin_url_gets_super_url_when_registered(self):
        try:
            from apps.schools.super_admin_bridge_registry import PLATFORM_ADMIN_BRIDGES
        except ImportError:
            self.skipTest("bridge registry unavailable")
        if not PLATFORM_ADMIN_BRIDGES:
            self.skipTest("no bridges configured")
        bridge_key, cfg = next(iter(PLATFORM_ADMIN_BRIDGES.items()))
        admin_url = cfg.get("admin_url")
        if not admin_url:
            self.skipTest("bridge has no admin_url")
        app_list = [
            {
                "app_label": "testapp",
                "name": "Test",
                "section": "Platform Configuration",
                "models": [
                    {
                        "name": "Bridged model",
                        "object_name": "Bridged",
                        "admin_url": admin_url,
                    },
                ],
            },
        ]
        catalog = build_platform_admin_catalog(app_list)
        row = catalog["entries"][0]
        self.assertEqual(row["bridge_key"], bridge_key)
        self.assertEqual(
            row["super_url"],
            reverse("super:admin_bridge", kwargs={"bridge_key": bridge_key}),
        )

    def test_enrich_app_index_models_adds_super_url(self):
        try:
            from apps.schools.super_admin_bridge_registry import PLATFORM_ADMIN_BRIDGES
        except ImportError:
            self.skipTest("bridge registry unavailable")
        if not PLATFORM_ADMIN_BRIDGES:
            self.skipTest("no bridges configured")
        bridge_key, cfg = next(iter(PLATFORM_ADMIN_BRIDGES.items()))
        admin_url = cfg.get("admin_url")
        if not admin_url:
            self.skipTest("bridge has no admin_url")
        enriched = enrich_app_index_models(
            {
                "models": [
                    {
                        "name": "X",
                        "object_name": "X",
                        "admin_url": admin_url,
                    }
                ]
            }
        )
        self.assertEqual(len(enriched), 1)
        self.assertTrue(enriched[0].get("super_url"))
