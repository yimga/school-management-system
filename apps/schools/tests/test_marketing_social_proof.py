"""Tests for the marketing social-proof source of truth.

These tests are the guardrail proving the platform pages ship with NO
fabricated customer proof: every helper must return empty/None by default and
must look slugs up case-insensitively.
"""

from __future__ import annotations

from django.test import SimpleTestCase, TestCase

from apps.schools.marketing_social_proof import (
    CASE_STUDIES,
    LOGOS,
    TESTIMONIALS,
    aggregate_rating_for_slug,
    case_study_for_slug,
    logos_for_slug,
    review_schema_for_slug,
    testimonials_for_slug,
)

# The marketing platform-page slugs the bands attach to.
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


class MarketingSocialProofMapsAreEmptyTests(SimpleTestCase):
    """No fabricated proof ships — the SOT maps start empty (no DB needed)."""

    def test_data_maps_are_empty_by_default(self) -> None:
        self.assertEqual(TESTIMONIALS, {})
        self.assertEqual(LOGOS, {})
        self.assertEqual(CASE_STUDIES, {})


class MarketingSocialProofEmptyByDefaultTests(TestCase):
    """Every helper returns empty/None with no approved config + no DB rows.

    Uses ``TestCase`` (DB-enabled, empty test DB) so the defensive DB path in
    ``testimonials_for_slug`` runs against a real-but-empty table and still
    yields ``[]`` — proving honesty holds even after the migration lands.
    """

    def test_testimonials_empty_for_every_platform_slug(self) -> None:
        for slug in PLATFORM_SLUGS:
            with self.subTest(slug=slug):
                self.assertEqual(testimonials_for_slug(slug), [])

    def test_logos_empty_for_every_platform_slug(self) -> None:
        for slug in PLATFORM_SLUGS:
            with self.subTest(slug=slug):
                self.assertEqual(logos_for_slug(slug), [])

    def test_case_study_none_for_every_platform_slug(self) -> None:
        for slug in PLATFORM_SLUGS:
            with self.subTest(slug=slug):
                self.assertIsNone(case_study_for_slug(slug))

    def test_unknown_and_falsy_slugs_return_empty(self) -> None:
        for slug in ("does-not-exist", "", "   "):
            with self.subTest(slug=slug):
                self.assertEqual(testimonials_for_slug(slug), [])
                self.assertEqual(logos_for_slug(slug), [])
                self.assertIsNone(case_study_for_slug(slug))


class MarketingSocialProofLookupTests(TestCase):
    """Lookups are case-insensitive and whitespace-tolerant."""

    def test_testimonials_lookup_is_case_insensitive(self) -> None:
        for slug in PLATFORM_SLUGS:
            with self.subTest(slug=slug):
                self.assertEqual(
                    testimonials_for_slug(slug),
                    testimonials_for_slug(slug.upper()),
                )
                self.assertEqual(
                    testimonials_for_slug(slug),
                    testimonials_for_slug(f"  {slug.title()}  "),
                )

    def test_logos_lookup_is_case_insensitive(self) -> None:
        for slug in PLATFORM_SLUGS:
            with self.subTest(slug=slug):
                self.assertEqual(
                    logos_for_slug(slug),
                    logos_for_slug(slug.upper()),
                )
                self.assertEqual(
                    logos_for_slug(slug),
                    logos_for_slug(f"  {slug.title()}  "),
                )

    def test_case_study_lookup_is_case_insensitive(self) -> None:
        for slug in PLATFORM_SLUGS:
            with self.subTest(slug=slug):
                self.assertEqual(
                    case_study_for_slug(slug),
                    case_study_for_slug(slug.upper()),
                )
                self.assertEqual(
                    case_study_for_slug(slug),
                    case_study_for_slug(f"  {slug.title()}  "),
                )


class MarketingSocialProofSeoSchemaEmptyByDefaultTests(TestCase):
    """AggregateRating + Review JSON-LD never fabricate a rating.

    With no approved config testimonials and no approved DB rows, both helpers
    return ``None`` for every platform slug — so search engines never receive a
    fake ``ratingValue`` / ``reviewCount``.
    """

    def test_aggregate_rating_none_for_every_platform_slug(self) -> None:
        for slug in PLATFORM_SLUGS:
            with self.subTest(slug=slug):
                self.assertIsNone(aggregate_rating_for_slug(slug))

    def test_review_schema_none_for_every_platform_slug(self) -> None:
        for slug in PLATFORM_SLUGS:
            with self.subTest(slug=slug):
                self.assertIsNone(
                    review_schema_for_slug(slug, name="RunMyCampus Admissions")
                )

    def test_aggregate_and_review_none_for_unknown_and_falsy_slugs(self) -> None:
        for slug in ("does-not-exist", "", "   "):
            with self.subTest(slug=slug):
                self.assertIsNone(aggregate_rating_for_slug(slug))
                self.assertIsNone(review_schema_for_slug(slug, name="RunMyCampus"))

    def test_lang_argument_accepted_and_still_empty(self) -> None:
        for slug in PLATFORM_SLUGS:
            with self.subTest(slug=slug):
                self.assertEqual(testimonials_for_slug(slug, lang="fr"), [])
                self.assertIsNone(aggregate_rating_for_slug(slug, lang="fr"))
                self.assertIsNone(
                    review_schema_for_slug(slug, name="RunMyCampus", lang="fr")
                )
