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
                "Pricing",
                "Trust",
                "Resources",
            ],
        )

    def test_solutions_dropdown_maps_buyer_segments(self):
        from apps.schools.marketing_v3_surfaces import marketing_verb_nav_enabled

        if marketing_verb_nav_enabled():
            self.skipTest("verb nav replaces legacy Solutions mega menu")
        nav = _marketing_navbar_primary()
        sol = next(i for i in nav if i["label"] == "Solutions")
        child_labels = [c["label"] for c in sol["children"] if not c.get("is_header")]
        self.assertIn("Private schools", child_labels)
        self.assertIn("School networks", child_labels)
        self.assertIn("Low-connectivity schools", child_labels)
        self.assertIn("Finance teams", child_labels)
        self.assertIn("Teachers & academics", child_labels)
        self.assertIn("Parents & families", child_labels)

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
