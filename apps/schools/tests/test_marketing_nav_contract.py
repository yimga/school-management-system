"""Fast, DB-free checks for public marketing navbar IA (split for quick local runs)."""

from django.test import SimpleTestCase

from apps.schools.marketing_views import (
    _marketing_navbar_primary,
    _topical_nav,
    _topical_nav_featured,
)


class MarketingNavContractTests(SimpleTestCase):
    def test_navbar_primary_has_six_top_labels(self):
        from apps.schools.marketing_v3_surfaces import marketing_verb_nav_enabled

        nav = _marketing_navbar_primary()
        labels = [str(item["label"]) for item in nav]
        if marketing_verb_nav_enabled():
            self.assertIn("Run", labels)
            self.assertIn("Teach", labels)
            self.assertIn("Pricing", labels)
            self.assertGreaterEqual(len(labels), 5)
            return
        self.assertEqual(
            labels,
            [
                "Platform",
                "Solutions",
                "Why RunMyCampus",
                "Experience",
                "Pricing",
                "Resources",
                "More",
            ],
        )
        why = next(i for i in nav if i["label"] == "Why RunMyCampus")
        self.assertTrue(why.get("mega_columns"))
        self.assertNotIn("Trust", labels)
        more = next(i for i in nav if i["label"] == "More")
        self.assertTrue(more.get("mega_columns"))

    def test_solutions_dropdown_is_only_buyer_worlds(self):
        from apps.schools.marketing_v3_surfaces import marketing_verb_nav_enabled

        if marketing_verb_nav_enabled():
            self.skipTest("verb nav replaces legacy Solutions mega menu")
        nav = _marketing_navbar_primary()
        sol = next(i for i in nav if i["label"] == "Solutions")
        child_labels = [c["label"] for c in sol["children"] if not c.get("is_header")]
        self.assertEqual(
            child_labels,
            [
                "Solutions overview",
                "Private Schools",
                "International Schools",
                "K-12 Schools",
                "Multi-Campus Groups",
                "Faith-Based Schools",
                "Growing School Networks",
            ],
        )
        column_titles = [col["title"] for col in sol["mega_columns"]]
        self.assertEqual(column_titles, ["School models", "Networks & communities"])

    def test_primary_nav_includes_storefront_link(self):
        from django.urls import reverse

        from apps.schools.marketing_v3_surfaces import (
            marketing_navbar_verb_primary,
            marketing_verb_nav_enabled,
        )

        storefront = reverse("marketing_intent_homepage")

        def _flat_top_level_paths(items: list[dict]) -> list[str]:
            return [str(item.get("path") or "") for item in items if item.get("path")]

        legacy_paths = _flat_top_level_paths(_marketing_navbar_primary())
        self.assertIn(storefront, legacy_paths)

        if marketing_verb_nav_enabled():
            verb_paths = _flat_top_level_paths(marketing_navbar_verb_primary())
            self.assertIn(storefront, verb_paths)

    def test_topical_nav_featured_is_bounded_and_subset_of_full(self):
        full = _topical_nav()
        feat = _topical_nav_featured()
        self.assertLessEqual(len(feat), 4)
        self.assertLessEqual(len(feat), len(full))
        if len(full) > 4:
            self.assertLess(len(feat), len(full))
        full_paths = {x["path"] for x in full}
        for item in feat:
            self.assertIn(item["path"], full_paths)
            self.assertTrue(item["path"].startswith("/solutions/"))
