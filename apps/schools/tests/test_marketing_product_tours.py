"""Tests for the marketing product-tour SOT."""

from __future__ import annotations

from django.test import SimpleTestCase

from apps.schools.marketing_product_tours import (
    flagship_tour_slugs,
    product_tour_for_slug,
)

FLAGSHIP_SLUGS = [
    "platform-student-information-system",
    "platform-attendance",
    "platform-fees-payments",
    "platform-communications",
    "platform-admissions",
    "platform-grading-report-cards",
]


class ProductTourSOTTests(SimpleTestCase):
    def test_every_flagship_slug_returns_at_least_three_frames(self):
        for slug in FLAGSHIP_SLUGS:
            with self.subTest(slug=slug):
                tour = product_tour_for_slug(slug)
                self.assertIsNotNone(tour, f"{slug} should resolve a tour")
                self.assertEqual(tour["slug"], slug)
                self.assertGreaterEqual(
                    len(tour["frames"]),
                    3,
                    f"{slug} should have >= 3 frames",
                )

    def test_every_frame_has_non_empty_required_keys(self):
        for slug in FLAGSHIP_SLUGS:
            tour = product_tour_for_slug(slug)
            for frame in tour["frames"]:
                with self.subTest(slug=slug, key=frame.get("key")):
                    for field in ("key", "caption", "tooltip", "ui_kind"):
                        self.assertIn(field, frame)
                        self.assertTrue(
                            isinstance(frame[field], str) and frame[field].strip(),
                            f"{slug}:{field} must be a non-empty string",
                        )

    def test_lookup_is_case_insensitive(self):
        upper = product_tour_for_slug("PLATFORM-ATTENDANCE")
        mixed = product_tour_for_slug("Platform-Attendance  ")
        self.assertIsNotNone(upper)
        self.assertIsNotNone(mixed)
        self.assertEqual(upper["slug"], "platform-attendance")
        self.assertEqual(mixed["slug"], "platform-attendance")

    def test_unknown_slug_returns_none(self):
        self.assertIsNone(product_tour_for_slug("platform-does-not-exist"))

    def test_empty_slug_returns_none(self):
        self.assertIsNone(product_tour_for_slug(""))
        self.assertIsNone(product_tour_for_slug(None))  # type: ignore[arg-type]

    def test_frame_keys_are_unique_within_a_tour(self):
        for slug in FLAGSHIP_SLUGS:
            tour = product_tour_for_slug(slug)
            keys = [f["key"] for f in tour["frames"]]
            self.assertEqual(len(keys), len(set(keys)), f"{slug} keys must be unique")

    def test_returned_frames_are_a_copy(self):
        tour = product_tour_for_slug("platform-attendance")
        tour["frames"].append({"key": "x", "caption": "x", "tooltip": "x", "ui_kind": "x"})
        again = product_tour_for_slug("platform-attendance")
        self.assertEqual(len(again["frames"]), 3)

    def test_flagship_tour_slugs_covers_all_required(self):
        slugs = flagship_tour_slugs()
        for slug in FLAGSHIP_SLUGS:
            self.assertIn(slug, slugs)

    # --- Localization -----------------------------------------------------

    def test_default_lang_is_english(self):
        default = product_tour_for_slug("platform-attendance")
        explicit = product_tour_for_slug("platform-attendance", lang="en")
        self.assertEqual(default, explicit)

    def test_french_translates_caption_and_tooltip(self):
        en = product_tour_for_slug("platform-attendance", lang="en")
        fr = product_tour_for_slug("platform-attendance", lang="fr")
        self.assertEqual(en["slug"], fr["slug"])
        self.assertEqual(len(en["frames"]), len(fr["frames"]))
        # Stable enum keys are preserved untranslated.
        self.assertEqual(
            [f["key"] for f in en["frames"]],
            [f["key"] for f in fr["frames"]],
        )
        self.assertEqual(
            [f["ui_kind"] for f in en["frames"]],
            [f["ui_kind"] for f in fr["frames"]],
        )
        # But caption + tooltip are translated.
        self.assertNotEqual(en["frames"][0]["caption"], fr["frames"][0]["caption"])
        self.assertNotEqual(en["frames"][0]["tooltip"], fr["frames"][0]["tooltip"])

    def test_arabic_returns_proper_arabic(self):
        ar = product_tour_for_slug("platform-attendance", lang="ar")
        en = product_tour_for_slug("platform-attendance", lang="en")
        self.assertNotEqual(en["frames"][0]["caption"], ar["frames"][0]["caption"])
        self.assertTrue(
            any("؀" <= ch <= "ۿ" for ch in ar["frames"][0]["caption"]),
            "Arabic caption must contain Arabic-script characters",
        )

    def test_unknown_lang_falls_back_to_english(self):
        en = product_tour_for_slug("platform-attendance", lang="en")
        zz = product_tour_for_slug("platform-attendance", lang="zz")
        self.assertEqual(en, zz)

    def test_regional_variant_resolves_to_base_lang(self):
        pt = product_tour_for_slug("platform-attendance", lang="pt")
        pt_br = product_tour_for_slug("platform-attendance", lang="pt-BR")
        self.assertEqual(pt, pt_br)

    def test_localized_frames_are_a_copy(self):
        fr = product_tour_for_slug("platform-attendance", lang="fr")
        fr["frames"].append(
            {"key": "x", "caption": "x", "tooltip": "x", "ui_kind": "x"}
        )
        again = product_tour_for_slug("platform-attendance", lang="fr")
        self.assertEqual(len(again["frames"]), 3)

    def test_unknown_slug_returns_none_for_any_lang(self):
        self.assertIsNone(product_tour_for_slug("nope", lang="fr"))
        self.assertIsNone(product_tour_for_slug("", lang="ar"))
