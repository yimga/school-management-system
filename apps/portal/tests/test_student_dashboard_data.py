"""Student role-home data bundle — degrade-safe defaults."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from apps.portal.student_dashboard_data import build_student_home_extras
from apps.portal.student_results_visibility import (
    STUDENT_RESULTS_VISIBILITY_ENTERED,
    STUDENT_RESULTS_VISIBILITY_OFF,
)


class BuildStudentHomeExtrasTests(SimpleTestCase):
    def test_no_profile_returns_empty_enrichment_with_unread_metric(self):
        request = SimpleNamespace(school=None)
        out = build_student_home_extras(request, None, unread=3, year=None, term=None)

        self.assertIsNone(out["student_attendance_pct"])
        self.assertEqual(out["student_due_items"], [])
        self.assertEqual(len(out["student_metrics"]), 1)
        self.assertEqual(out["student_metrics"][0]["label"], "Unread")
        self.assertEqual(out["student_metrics"][0]["value"], 3)
        self.assertIn("Student home", out["student_hero_eyebrow"])

    @patch("apps.siteconfig.config_service.get_effective_site_settings")
    @patch("apps.portal.student_dashboard_data._student_due_items", return_value=[])
    @patch("apps.people.models.Badge.objects.filter")
    @patch("apps.portal.services._attendance_snapshot", return_value={"overall": 92})
    @patch("apps.portal.services._performance_overview", return_value={"average": 14.5})
    @patch("apps.portal.services._grade_trend", return_value=[{"label": "W1", "value": 70}, {"label": "W2", "value": 82}])
    @patch("apps.portal.services._timetable_overview", return_value=[{"subject": "Math"}])
    @patch("apps.portal.services._subject_performance", return_value=[{"subject": "Math", "average": 15}])
    @patch("apps.portal.services._attendance_trend", return_value=[{"label": "M", "value": 90}])
    @patch("apps.reports.services.is_term_published", return_value=True)
    def test_profile_with_year_term_populates_metrics(
        self,
        _published,
        _att_trend,
        _subjects,
        _timetable,
        _grade_trend,
        _perf,
        _att_snap,
        _badge_filter,
        _due,
        _site,
    ):
        _site.return_value = SimpleNamespace(portal_announcements=[])
        _badge_filter.return_value.order_by.return_value = []
        profile = SimpleNamespace(classroom=SimpleNamespace(id=1), classroom_id=1)
        year = SimpleNamespace(id=1, name="2025-2026")
        term = SimpleNamespace(id=2, label="Term 1", name="Term 1")
        request = MagicMock()
        request.school = SimpleNamespace(id=99)

        out = build_student_home_extras(
            request, profile, unread=0, year=year, term=term
        )

        self.assertEqual(out["student_attendance_pct"], 92)
        self.assertEqual(out["student_grade_avg"], 14.5)
        labels = [m["label"] for m in out["student_metrics"]]
        self.assertIn("Attendance", labels)
        self.assertIn("Average", labels)
        self.assertIsNotNone(out["student_ai_insight"])

    @patch("apps.siteconfig.config_service.get_effective_site_settings")
    @patch("apps.portal.student_dashboard_data._student_due_items", return_value=[])
    @patch("apps.people.models.Badge.objects.filter")
    @patch("apps.portal.services._attendance_snapshot", return_value={"overall": 88})
    @patch("apps.portal.services._performance_overview", return_value={"average": 12.0})
    @patch("apps.portal.services._grade_trend", return_value=[{"label": "W1", "value": 60}])
    @patch("apps.portal.services._timetable_overview", return_value=[])
    @patch("apps.portal.services._subject_performance", return_value=[{"subject": "Math", "average": 14}])
    @patch("apps.portal.services._attendance_trend", return_value=[])
    @patch("apps.reports.services.is_term_published", return_value=False)
    def test_entered_mode_shows_grades_without_publish(
        self,
        _published,
        _att_trend,
        _subjects,
        _timetable,
        _grade_trend,
        _perf,
        _att_snap,
        _badge_filter,
        _due,
        _site,
    ):
        _site.return_value = SimpleNamespace(
            portal_announcements=[],
            student_results_visibility=STUDENT_RESULTS_VISIBILITY_ENTERED,
        )
        _badge_filter.return_value.order_by.return_value = []
        profile = SimpleNamespace(classroom=SimpleNamespace(id=1), classroom_id=1)
        year = SimpleNamespace(id=1, name="2025-2026")
        term = SimpleNamespace(id=2, label="Term 1", name="Term 1")
        request = MagicMock()
        request.school = SimpleNamespace(id=99)

        out = build_student_home_extras(
            request, profile, unread=0, year=year, term=term
        )

        self.assertTrue(out["student_can_view_results"])
        self.assertFalse(out["student_results_locked"])
        self.assertEqual(
            out["student_results_visibility_mode"], STUDENT_RESULTS_VISIBILITY_ENTERED
        )

    @patch("apps.siteconfig.config_service.get_effective_site_settings")
    @patch("apps.portal.student_dashboard_data._student_due_items", return_value=[])
    @patch("apps.people.models.Badge.objects.filter")
    @patch("apps.portal.services._attendance_snapshot", return_value={"overall": 88})
    @patch("apps.portal.services._performance_overview", return_value={"average": 12.0})
    @patch("apps.portal.services._grade_trend", return_value=[{"label": "W1", "value": 60}])
    @patch("apps.portal.services._timetable_overview", return_value=[])
    @patch("apps.portal.services._subject_performance", return_value=[{"subject": "Math", "average": 14}])
    @patch("apps.portal.services._attendance_trend", return_value=[])
    @patch("apps.reports.services.is_term_published", return_value=False)
    def test_off_mode_hides_grades(
        self,
        _published,
        _att_trend,
        _subjects,
        _timetable,
        _grade_trend,
        _perf,
        _att_snap,
        _badge_filter,
        _due,
        _site,
    ):
        _site.return_value = SimpleNamespace(
            portal_announcements=[],
            student_results_visibility=STUDENT_RESULTS_VISIBILITY_OFF,
        )
        _badge_filter.return_value.order_by.return_value = []
        profile = SimpleNamespace(classroom=SimpleNamespace(id=1), classroom_id=1)
        year = SimpleNamespace(id=1, name="2025-2026")
        term = SimpleNamespace(id=2, label="Term 1", name="Term 1")
        request = MagicMock()
        request.school = SimpleNamespace(id=99)

        out = build_student_home_extras(
            request, profile, unread=0, year=year, term=term
        )

        self.assertFalse(out["student_can_view_results"])
        self.assertFalse(out["student_results_locked"])
        self.assertEqual(out["student_subject_rows"], [])
        labels = [m["label"] for m in out["student_metrics"]]
        self.assertNotIn("Average", labels)
