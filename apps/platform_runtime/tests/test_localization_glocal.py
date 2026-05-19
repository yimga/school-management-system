"""Glocal pressure-test regressions for platform_runtime.localization."""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from unittest import TestCase

from apps.platform_runtime.localization import (
    CALENDAR_HIJRI,
    calendar_type_for_school,
    calendar_week_bounds,
    format_school_date,
    school_week_for_date,
)


class LocalizationGlocalTests(TestCase):
    def test_format_school_date_dd_mm_yyyy(self):
        d = date(2026, 5, 18)
        self.assertEqual(format_school_date(d, date_format="DD/MM/YYYY"), "18/05/2026")

    def test_calendar_type_reads_region_calendar_system(self):
        region = SimpleNamespace(calendar_system="islamic")
        school = SimpleNamespace(default_region_id="SAU", default_region=region)
        self.assertEqual(calendar_type_for_school(school), CALENDAR_HIJRI)

    def test_calendar_week_bounds_sunday_start(self):
        d = date(2026, 5, 18)  # Monday
        start, end = calendar_week_bounds(d, week_start_day=6)
        self.assertEqual(start, date(2026, 5, 17))
        self.assertEqual(end, date(2026, 5, 23))

    def test_school_week_respects_week_start_sunday(self):
        # Academic year starts Monday 2025-09-01; Sunday 2025-09-07 is still week 1
        # when week starts on Sunday (US-style boundary)
        d = date(2025, 9, 7)
        start = date(2025, 9, 1)
        monday_week = school_week_for_date(d, academic_year_start=start, week_start_day=0)
        sunday_week = school_week_for_date(d, academic_year_start=start, week_start_day=6)
        self.assertGreaterEqual(monday_week, 1)
        self.assertGreaterEqual(sunday_week, 1)
        self.assertNotEqual(monday_week, sunday_week)
