"""Tests for the honest vs-competitor comparison SOT."""

from __future__ import annotations

from django.test import SimpleTestCase

from apps.schools.marketing_competitor_comparisons import (
    all_comparison_slugs,
    comparison_for_slug,
)

# Capability cells RunMyCampus asserts — each must map to a SHIPPED capability.
_SHIPPED_SIGNALS = (
    "offline-first",
    "mobile-money",
    "tenant",
    "oneroster",
    "emis",
    "governance",
)


class CompetitorComparisonTests(SimpleTestCase):
    def test_expected_competitors(self):
        self.assertEqual(
            sorted(all_comparison_slugs()), ["arbor", "blackbaud", "powerschool"]
        )

    def test_each_has_rows_and_disclaimer(self):
        for slug in all_comparison_slugs():
            cmp = comparison_for_slug(slug)
            self.assertIsNotNone(cmp)
            self.assertGreaterEqual(len(cmp["rows"]), 4)
            self.assertIn("public marketing", cmp["disclaimer"].lower())
            self.assertTrue(cmp["seo_title"])
            self.assertTrue(cmp["seo_description"])

    def test_runmycampus_cells_reference_shipped_capabilities(self):
        # The aggregate of our cells must mention the shipped differentiators,
        # so we never claim something outside the feature-gap register.
        for slug in all_comparison_slugs():
            cmp = comparison_for_slug(slug)
            ours_blob = " ".join(r["runmycampus"] for r in cmp["rows"]).lower()
            for signal in _SHIPPED_SIGNALS:
                self.assertIn(
                    signal, ours_blob, f"{slug}: missing shipped signal '{signal}'"
                )

    def test_case_insensitive_and_unknown(self):
        self.assertIsNotNone(comparison_for_slug("PowerSchool"))
        self.assertIsNone(comparison_for_slug("nope"))

    def test_no_empty_competitor_cells(self):
        for slug in all_comparison_slugs():
            cmp = comparison_for_slug(slug)
            for row in cmp["rows"]:
                self.assertTrue(row["competitor"], f"{slug}/{row['capability']} empty")
