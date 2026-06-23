"""Student dashboard grade visibility policy."""

from __future__ import annotations

from django.test import SimpleTestCase

from apps.portal.student_results_visibility import (
    DEFAULT_STUDENT_RESULTS_VISIBILITY,
    STUDENT_RESULTS_VISIBILITY_ENTERED,
    STUDENT_RESULTS_VISIBILITY_OFF,
    STUDENT_RESULTS_VISIBILITY_PUBLISHED,
    get_student_results_visibility_from_site,
    normalize_student_results_visibility,
    resolve_student_grade_dashboard_access,
)


class NormalizeStudentResultsVisibilityTests(SimpleTestCase):
    def test_blank_defaults_to_published(self):
        self.assertEqual(
            normalize_student_results_visibility(None),
            DEFAULT_STUDENT_RESULTS_VISIBILITY,
        )
        self.assertEqual(
            normalize_student_results_visibility(""),
            STUDENT_RESULTS_VISIBILITY_PUBLISHED,
        )

    def test_unknown_values_fallback(self):
        self.assertEqual(
            normalize_student_results_visibility("bogus"),
            STUDENT_RESULTS_VISIBILITY_PUBLISHED,
        )

    def test_valid_modes(self):
        for mode in (
            STUDENT_RESULTS_VISIBILITY_OFF,
            STUDENT_RESULTS_VISIBILITY_PUBLISHED,
            STUDENT_RESULTS_VISIBILITY_ENTERED,
        ):
            self.assertEqual(normalize_student_results_visibility(mode), mode)


class ResolveStudentGradeDashboardAccessTests(SimpleTestCase):
    def test_off_hides_even_when_published(self):
        out = resolve_student_grade_dashboard_access(
            visibility_mode=STUDENT_RESULTS_VISIBILITY_OFF,
            term_published=True,
            has_grade_data=True,
        )
        self.assertFalse(out["can_view_results"])
        self.assertFalse(out["results_locked"])

    def test_published_requires_publish(self):
        hidden = resolve_student_grade_dashboard_access(
            visibility_mode=STUDENT_RESULTS_VISIBILITY_PUBLISHED,
            term_published=False,
            has_grade_data=True,
        )
        self.assertFalse(hidden["can_view_results"])
        self.assertTrue(hidden["results_locked"])

        shown = resolve_student_grade_dashboard_access(
            visibility_mode=STUDENT_RESULTS_VISIBILITY_PUBLISHED,
            term_published=True,
            has_grade_data=True,
        )
        self.assertTrue(shown["can_view_results"])
        self.assertFalse(shown["results_locked"])

    def test_entered_shows_without_publish(self):
        out = resolve_student_grade_dashboard_access(
            visibility_mode=STUDENT_RESULTS_VISIBILITY_ENTERED,
            term_published=False,
            has_grade_data=True,
        )
        self.assertTrue(out["can_view_results"])
        self.assertFalse(out["results_locked"])

    def test_entered_without_data_stays_empty(self):
        out = resolve_student_grade_dashboard_access(
            visibility_mode=STUDENT_RESULTS_VISIBILITY_ENTERED,
            term_published=True,
            has_grade_data=False,
        )
        self.assertFalse(out["can_view_results"])


class GetStudentResultsVisibilityFromSiteTests(SimpleTestCase):
    def test_reads_site_attribute(self):
        site = type("S", (), {"student_results_visibility": "entered"})()
        self.assertEqual(
            get_student_results_visibility_from_site(site),
            STUDENT_RESULTS_VISIBILITY_ENTERED,
        )

    def test_none_site_defaults(self):
        self.assertEqual(
            get_student_results_visibility_from_site(None),
            DEFAULT_STUDENT_RESULTS_VISIBILITY,
        )
