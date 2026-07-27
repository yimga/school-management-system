"""Admin-published holidays must appear in the parent/teacher unified calendar.

The HolidayCalendar (term breaks, public/religious holidays, exam periods) was
admin-only — configured in Django/tenant admin but never rendered to families or
staff. The unified calendar now merges it alongside grading deadlines + school
events, so the admin-published academic calendar is visible where people look.
"""

from __future__ import annotations

from datetime import date, timedelta

from django.test import TestCase

from apps.portal.services import _merged_upcoming_events, _upcoming_holidays


class UnifiedCalendarHolidayTests(TestCase):
    def setUp(self):
        from apps.academics.models import AcademicYear
        from apps.academics.models_tenant_runtime import HolidayCalendar
        from apps.schools.models import School
        from apps.siteconfig.models_platform_catalog import RegionConfig

        self.school = School.objects.create(
            name="Holiday High", slug="holiday-high", subdomain="holiday-high",
            is_active=True, country_code="CM",
        )
        self.region = RegionConfig.objects.create(code="CM", name="Cameroon")
        self.year = AcademicYear.objects.create(
            name="2026/2027",
            start_date=date(2026, 9, 1),
            end_date=date(2027, 7, 31),
            is_active=True,
            school=self.school,
        )
        today = date.today()
        HolidayCalendar.objects.create(
            region=self.region,
            academic_year=self.year,
            name="Christmas Break",
            date_start=today + timedelta(days=7),
            date_end=today + timedelta(days=14),
            holiday_type="school_holiday",
        )
        # A holiday that has fully passed must NOT show.
        HolidayCalendar.objects.create(
            region=self.region,
            academic_year=self.year,
            name="Old Break",
            date_start=today - timedelta(days=30),
            date_end=today - timedelta(days=20),
            holiday_type="school_holiday",
        )

    def test_upcoming_holidays_scoped_and_future_only(self):
        rows = _upcoming_holidays(self.year, school=self.school)
        titles = {r["title"] for r in rows}
        self.assertIn("Christmas Break", titles)
        self.assertNotIn("Old Break", titles)  # already passed
        holiday = next(r for r in rows if r["title"] == "Christmas Break")
        self.assertEqual(holiday["kind"], "holiday")

    def test_holiday_appears_in_merged_unified_calendar(self):
        events = _merged_upcoming_events(self.year, school=self.school)
        kinds = {e.get("kind") for e in events}
        self.assertIn("holiday", kinds)
        self.assertTrue(any(e.get("title") == "Christmas Break" for e in events))

    def test_year_none_is_graceful(self):
        self.assertEqual(_upcoming_holidays(None, school=self.school), [])
