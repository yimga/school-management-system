"""Tests for the marketing outcome-stat source of truth."""

from __future__ import annotations

from django.test import SimpleTestCase

from apps.schools.marketing_outcome_stats import (
    OUTCOME_STATS,
    outcome_stats_for_slug,
)

PLATFORM_SLUGS = (
    "platform-admissions",
    "platform-fees-payments",
    "platform-student-information-system",
    "platform-attendance",
    "platform-analytics",
    "platform-security",
    "platform-parent-portal",
    "platform-teacher-portal",
    "platform-student-portal",
    "platform-communications",
    "platform-workflows",
    "platform-offline-first",
    "platform-grading-report-cards",
    "platform-integrations",
    "platform-control-plane",
    "platform-runtime",
    "platform-education-os",
    "platform-marketplace",
    "platform-migration-cloud",
)


class MarketingOutcomeStatsTests(SimpleTestCase):
    def test_every_platform_slug_has_at_least_two_stats(self) -> None:
        for slug in PLATFORM_SLUGS:
            with self.subTest(slug=slug):
                stats = outcome_stats_for_slug(slug)
                self.assertGreaterEqual(
                    len(stats), 2, f"{slug} must expose >= 2 outcome stats"
                )
                self.assertLessEqual(
                    len(stats), 4, f"{slug} should expose at most 4 outcome stats"
                )

    def test_every_stat_has_non_empty_value_label_basis(self) -> None:
        for slug, stats in OUTCOME_STATS.items():
            for index, stat in enumerate(stats):
                with self.subTest(slug=slug, index=index):
                    for key in ("value", "label", "basis"):
                        self.assertIn(key, stat)
                        self.assertIsInstance(stat[key], str)
                        self.assertTrue(
                            stat[key].strip(),
                            f"{slug}[{index}].{key} must be non-empty",
                        )

    def test_lookup_is_case_insensitive(self) -> None:
        for slug in PLATFORM_SLUGS:
            with self.subTest(slug=slug):
                lower = outcome_stats_for_slug(slug)
                upper = outcome_stats_for_slug(slug.upper())
                mixed = outcome_stats_for_slug(f"  {slug.title()}  ")
                self.assertEqual(lower, upper)
                self.assertEqual(lower, mixed)

    def test_unknown_slug_returns_empty_list(self) -> None:
        self.assertEqual(outcome_stats_for_slug("does-not-exist"), [])
        self.assertEqual(outcome_stats_for_slug(""), [])

    def test_basis_framing_is_honest(self) -> None:
        # Any stat that isn't a hard platform fact must be flagged illustrative.
        for slug, stats in OUTCOME_STATS.items():
            for index, stat in enumerate(stats):
                with self.subTest(slug=slug, index=index):
                    basis = stat["basis"].lower()
                    self.assertTrue(
                        basis == "platform capability"
                        or basis.startswith("illustrative"),
                        f"{slug}[{index}] basis must be a fact or illustrative",
                    )

    # --- Localization -----------------------------------------------------

    def test_default_lang_is_english(self) -> None:
        en = outcome_stats_for_slug("platform-admissions")
        explicit = outcome_stats_for_slug("platform-admissions", lang="en")
        self.assertEqual(en, explicit)
        self.assertEqual(
            en[0]["label"], "time from inquiry to enrolled decision"
        )

    def test_french_returns_non_english_label_and_basis(self) -> None:
        en = outcome_stats_for_slug("platform-admissions", lang="en")
        fr = outcome_stats_for_slug("platform-admissions", lang="fr")
        # Same shape + same numeric values.
        self.assertEqual(len(en), len(fr))
        self.assertEqual([s["value"] for s in en], [s["value"] for s in fr])
        # But the human-readable label + basis are translated.
        self.assertNotEqual(en[0]["label"], fr[0]["label"])
        self.assertNotEqual(en[0]["basis"], fr[0]["basis"])
        self.assertIn("demande", fr[0]["label"])

    def test_arabic_returns_proper_arabic(self) -> None:
        ar = outcome_stats_for_slug("platform-admissions", lang="ar")
        en = outcome_stats_for_slug("platform-admissions", lang="en")
        self.assertNotEqual(en[0]["label"], ar[0]["label"])
        # At least one Arabic-script codepoint present in the label.
        self.assertTrue(
            any("؀" <= ch <= "ۿ" for ch in ar[0]["label"]),
            "Arabic label must contain Arabic-script characters",
        )

    def test_unknown_lang_falls_back_to_english(self) -> None:
        en = outcome_stats_for_slug("platform-admissions", lang="en")
        zz = outcome_stats_for_slug("platform-admissions", lang="zz")
        self.assertEqual(en, zz)

    def test_regional_variant_resolves_to_base_lang(self) -> None:
        fr = outcome_stats_for_slug("platform-admissions", lang="fr")
        fr_fr = outcome_stats_for_slug("platform-admissions", lang="fr-FR")
        self.assertEqual(fr, fr_fr)

    def test_value_never_translated(self) -> None:
        for lang in ("en", "fr", "es", "pt", "ar", "sw", "ha", "yo"):
            stats = outcome_stats_for_slug("platform-admissions", lang=lang)
            self.assertEqual(stats[0]["value"], "−38%", lang)

    def test_localized_result_is_a_copy(self) -> None:
        # Mutating the returned list/dicts must not corrupt the registry.
        fr = outcome_stats_for_slug("platform-admissions", lang="fr")
        fr[0]["label"] = "MUTATED"
        again = outcome_stats_for_slug("platform-admissions", lang="fr")
        self.assertNotEqual(again[0]["label"], "MUTATED")
        en = outcome_stats_for_slug("platform-admissions", lang="en")
        en[0]["label"] = "MUTATED"
        again_en = outcome_stats_for_slug("platform-admissions", lang="en")
        self.assertNotEqual(again_en[0]["label"], "MUTATED")
