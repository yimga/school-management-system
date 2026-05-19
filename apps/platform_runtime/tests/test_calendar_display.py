"""Calendar display + registry seed contract."""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from unittest import TestCase

from apps.platform_runtime.calendar_display import format_dual_calendar_date
from apps.platform_runtime.localization import calendar_type_for_school


class CalendarDisplayTests(TestCase):
    def test_gregorian_only(self):
        school = SimpleNamespace(
            default_region_id="USA",
            default_region=SimpleNamespace(calendar_system="gregorian"),
        )
        out = format_dual_calendar_date(
            date(2026, 5, 18),
            school=school,
            date_format="DD/MM/YYYY",
        )
        self.assertEqual(out, "18/05/2026")

    def test_islamic_region_resolves(self):
        school = SimpleNamespace(
            default_region=SimpleNamespace(calendar_system="islamic"),
        )
        self.assertEqual(calendar_type_for_school(school), "hijri")

    def test_buddhist_annotation(self):
        out = format_dual_calendar_date(
            date(2026, 5, 18),
            calendar_type="buddhist",
            date_format="YYYY-MM-DD",
        )
        self.assertIn("2026-05-18", out)
        self.assertIn("BE 2569", out)
