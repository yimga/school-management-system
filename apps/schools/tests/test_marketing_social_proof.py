"""Tests for the marketing social-proof source of truth.

These tests are the guardrail proving the platform pages ship with NO
fabricated customer proof: every helper must return empty/None by default and
must look slugs up case-insensitively.
"""

from __future__ import annotations

from django.test import SimpleTestCase

from apps.schools.marketing_social_proof import (
    CASE_STUDIES,
    LOGOS,
    TESTIMONIALS,
    case_study_for_slug,
    logos_for_slug,
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


class MarketingSocialProofEmptyByDefaultTests(SimpleTestCase):
    """No fabricated proof ships — the SOT maps start empty."""

    def test_data_maps_are_empty_by_default(self) -> None:
        self.assertEqual(TESTIMONIALS, {})
        self.assertEqual(LOGOS, {})
        self.assertEqual(CASE_STUDIES, {})

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


class MarketingSocialProofLookupTests(SimpleTestCase):
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
