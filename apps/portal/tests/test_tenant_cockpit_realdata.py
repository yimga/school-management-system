"""Tenant cockpit real-data hydration (batch 1489)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone as dt_timezone
from decimal import Decimal
from unittest.mock import patch

from django.test import SimpleTestCase
from django.utils import timezone

from apps.accounts.models import User
from apps.portal.tenant_cockpit_realdata import (
    _format_widget_event,
    _hydrate_today_snapshot,
    _hydrate_year_progress,
    hydrate_role_home_cockpit_realdata,
    hydrate_year_progress_realdata,
)


def _make_year(start, end, eta="June 12"):
    class _Year:
        start_date = start
        end_date = end

        def format_end_date_display(self):
            return eta

    return _Year()


def _make_term(label="Term 2"):
    return type("_Term", (), {"label": label})()


class _ReqNoSchool:
    school = None


class TenantCockpitRealdataTests(SimpleTestCase):
    def test_format_widget_event_from_when_datetime(self):
        when = timezone.now() + timedelta(days=2)
        row = _format_widget_event(
            {
                "title": "Parent evening",
                "when": when,
                "detail": "Hall A",
            }
        )
        self.assertIsNotNone(row)
        assert row is not None
        self.assertEqual(row["title"], "Parent evening")
        self.assertEqual(row["meta"], "Hall A")
        self.assertIn(row["pill_tone"], ("", "today", "soon"))

    def test_format_widget_event_preserves_preformatted(self):
        row = _format_widget_event(
            {
                "day": "21",
                "month": "May",
                "title": "Sports day",
                "meta": "Field",
            }
        )
        self.assertEqual(row["day"], "21")
        self.assertEqual(row["title"], "Sports day")

    @patch("apps.portal.services.guardian_student_links", return_value=[])
    @patch("apps.portal.parent_portal_helpers.get_active_child_id", return_value=None)
    def test_hydrate_today_snapshot_enables_cards(self, _mock_child, _mock_links):
        class _Req:
            user = type("U", (), {"role": User.Role.PARENT, "pk": 1})()

        section = {"enabled": False, "cards": []}
        widget = {
            "attendance": {"overall": 92, "label": "Term"},
            "finance": {"balance": Decimal("10.00"), "overdue": 1, "label": "Fees"},
            "tasks": {"pending_evaluations": 1, "pending_payments": 0},
            "performance": {"average": 14.5, "label": "Grades"},
        }
        out = _hydrate_today_snapshot(_Req(), section, widget)
        self.assertTrue(out["enabled"])
        self.assertGreaterEqual(len(out["cards"]), 3)

    @patch("apps.portal.services.guardian_student_links", return_value=[])
    @patch("apps.portal.parent_portal_helpers.get_active_child_id", return_value=None)
    @patch("apps.portal.tenant_cockpit_realdata.is_tp_v3_role_home_request", return_value=True)
    @patch("apps.portal.tenant_cockpit_realdata._role_widget_bundle")
    def test_hydrate_role_home_overlays_sections(
        self, mock_bundle, _mock_role_home, _mock_child, _mock_links
    ):
        mock_bundle.return_value = {
            "attendance": {"overall": 88},
            "finance": {"balance": Decimal("0"), "overdue": 0},
            "tasks": {"pending_evaluations": 0, "pending_payments": 0},
            "events": [
                {
                    "title": "Deadline",
                    "when": datetime(2026, 6, 1, 12, 0, tzinfo=dt_timezone.utc),
                    "detail": "Seq 1",
                }
            ],
        }
        cockpit = {
            "today_snapshot": {"enabled": False, "cards": []},
            "upcoming_events": {"enabled": False, "events": []},
            "quick_actions": {"enabled": False, "tiles": []},
        }
        class _Req:
            user = type("U", (), {"role": User.Role.PARENT, "pk": 1})()

        out = hydrate_role_home_cockpit_realdata(_Req(), cockpit)
        self.assertTrue(out["today_snapshot"]["enabled"])
        self.assertTrue(out["upcoming_events"]["enabled"])
        self.assertGreaterEqual(len(out["upcoming_events"]["events"]), 1)

    @patch("apps.portal.tenant_cockpit_realdata.is_tp_v3_role_home_request", return_value=True)
    @patch("apps.portal.tenant_cockpit_realdata._role_widget_bundle")
    def test_teacher_role_home_hydrates_completion(self, mock_bundle, _mock_role_home):
        mock_bundle.return_value = {
            "attendance": {"overall": 91},
            "finance": {},
            "tasks": {"pending_evaluations": 3, "pending_payments": 0},
            "performance": {"average": 72, "label": "Marking completion"},
        }
        cockpit = {"today_snapshot": {"enabled": False, "cards": []}}
        class _Req:
            user = type("U", (), {"role": User.Role.TEACHER, "pk": 2})()

        out = hydrate_role_home_cockpit_realdata(_Req(), cockpit)
        self.assertTrue(out["today_snapshot"]["enabled"])
        values = [c.get("value") for c in out["today_snapshot"]["cards"]]
        self.assertIn("72", values)


class YearProgressHydrationTests(SimpleTestCase):
    """Live academic-year progress bar overlay (PII-safe, override-respecting)."""

    def _section(self, **overrides):
        base = {"enabled": True, "label": "Academic year", "term_label": "", "percent": 0, "eta_label": ""}
        base.update(overrides)
        return base

    @patch("apps.academics.services.get_active_year_and_term")
    def test_auto_derives_percent_term_and_eta(self, mock_active):
        today = timezone.localdate()
        mock_active.return_value = (
            _make_year(today - timedelta(days=50), today + timedelta(days=50)),
            _make_term("Term 2"),
        )
        out = _hydrate_year_progress(_ReqNoSchool(), self._section())
        # 50 of 100 days elapsed -> ~50%.
        self.assertEqual(out["percent"], 50)
        self.assertEqual(out["term_label"], "Term 2")
        self.assertIn("June 12", out["eta_label"])

    @patch("apps.academics.services.get_active_year_and_term")
    def test_percent_clamps_high_when_year_has_ended(self, mock_active):
        today = timezone.localdate()
        mock_active.return_value = (
            _make_year(today - timedelta(days=200), today - timedelta(days=100)),
            _make_term(),
        )
        out = _hydrate_year_progress(_ReqNoSchool(), self._section())
        self.assertEqual(out["percent"], 100)

    @patch("apps.academics.services.get_active_year_and_term")
    def test_percent_clamps_low_before_year_starts(self, mock_active):
        today = timezone.localdate()
        mock_active.return_value = (
            _make_year(today + timedelta(days=10), today + timedelta(days=110)),
            _make_term(),
        )
        out = _hydrate_year_progress(_ReqNoSchool(), self._section())
        self.assertEqual(out["percent"], 0)

    @patch("apps.academics.services.get_active_year_and_term")
    def test_respects_operator_opt_out(self, mock_active):
        out = _hydrate_year_progress(_ReqNoSchool(), self._section(enabled=False))
        self.assertEqual(out["percent"], 0)
        self.assertEqual(out["term_label"], "")
        mock_active.assert_not_called()

    @patch("apps.academics.services.get_active_year_and_term")
    def test_respects_operator_published_values(self, mock_active):
        out = _hydrate_year_progress(
            _ReqNoSchool(), self._section(term_label="Trimester 1", percent=33)
        )
        self.assertEqual(out["term_label"], "Trimester 1")
        self.assertEqual(out["percent"], 33)
        mock_active.assert_not_called()

    @patch("apps.academics.services.get_active_year_and_term", return_value=(None, None))
    def test_degrades_when_no_active_year(self, _mock_active):
        out = _hydrate_year_progress(_ReqNoSchool(), self._section())
        self.assertEqual(out["percent"], 0)
        self.assertEqual(out["term_label"], "")

    @patch("apps.academics.services.get_active_year_and_term")
    def test_degrades_on_zero_length_span(self, mock_active):
        today = timezone.localdate()
        mock_active.return_value = (_make_year(today, today), _make_term())
        out = _hydrate_year_progress(_ReqNoSchool(), self._section())
        self.assertEqual(out["percent"], 0)

    @patch("apps.academics.services.get_active_year_and_term")
    def test_orchestrator_overlays_year_progress_key(self, mock_active):
        today = timezone.localdate()
        mock_active.return_value = (
            _make_year(today - timedelta(days=25), today + timedelta(days=75)),
            _make_term("Term 1"),
        )
        cockpit = {"year_progress": self._section()}
        out = hydrate_year_progress_realdata(_ReqNoSchool(), cockpit)
        self.assertEqual(out["year_progress"]["percent"], 25)
        self.assertEqual(out["year_progress"]["term_label"], "Term 1")

    def test_orchestrator_no_op_when_section_absent(self):
        cockpit = {"today_snapshot": {"enabled": True}}
        out = hydrate_year_progress_realdata(_ReqNoSchool(), cockpit)
        self.assertEqual(out, cockpit)
