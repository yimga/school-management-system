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
    hydrate_role_home_cockpit_realdata,
)


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
    @patch("apps.portal.tenant_cockpit_realdata._parent_widget_bundle")
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
