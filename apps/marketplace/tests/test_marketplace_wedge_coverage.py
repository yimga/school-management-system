"""First-party catalog must tag every SOT wedge 1–45 (kits ↔ wedges)."""

from django.test import SimpleTestCase

from apps.marketplace.management.commands.seed_marketplace_apps import FIRST_PARTY_APPS


class MarketplaceWedgeCoverageTests(SimpleTestCase):
    def test_first_party_wedge_ids_cover_1_through_45(self):
        seen: set[int] = set()
        for app in FIRST_PARTY_APPS:
            manifest = app.get("manifest") or {}
            wids = manifest.get("wedge_ids") or []
            self.assertIsInstance(
                wids,
                list,
                msg=f"{app.get('slug')}: wedge_ids must be a list",
            )
            for x in wids:
                n = int(x)
                self.assertGreaterEqual(n, 1, msg=app.get("slug"))
                self.assertLessEqual(n, 45, msg=app.get("slug"))
                seen.add(n)
        missing = set(range(1, 46)) - seen
        self.assertFalse(
            missing,
            msg=f"wedge_ids must cover every wedge 1–45; missing {sorted(missing)}",
        )

    def test_each_first_party_app_declares_wedge_ids(self):
        for app in FIRST_PARTY_APPS:
            wids = (app.get("manifest") or {}).get("wedge_ids")
            self.assertIsNotNone(
                wids,
                msg=f"{app['slug']}: manifest.wedge_ids required (empty list forbidden)",
            )
            self.assertTrue(
                len(wids) > 0,
                msg=f"{app['slug']}: manifest.wedge_ids must be non-empty",
            )
