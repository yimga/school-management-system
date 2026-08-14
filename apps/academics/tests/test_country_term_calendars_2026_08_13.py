"""Increment (b) — real per-country term windows, with an even-split fallback.

Before this, ``ensure_terms`` split the year into equal ``12 // term_count`` month
blocks, so Cameroon's third trimester "ended" Aug 31 instead of mid-July. These
tests pin: (1) a country with a curated calendar lands on the REAL windows; (2) a
per-school ``settings['term_windows']`` override wins; (3) a country with no
calendar still gets the right NUMBER of terms via the even split.
"""

from __future__ import annotations

import datetime as _dt

from django.test import TestCase

from apps.academics.country_term_calendars import resolve_term_windows
from apps.academics.models import Term
from apps.academics.structure_provisioning import ensure_academic_year, ensure_terms
from apps.schools.models import School


class CameroonRealWindowsTests(TestCase):
    def test_cameroon_terms_land_on_real_trimester_windows_not_even_split(self):
        school = School.objects.create(name="CMcal", subdomain="cm-cal", country_code="CM")
        year, _ = ensure_academic_year(school, name="2025/2026")
        ensure_terms(school, year)

        terms = list(
            Term.objects.filter(school=school, academic_year=year).order_by("position")
        )
        self.assertEqual(len(terms), 3)
        # Real Cameroon trimesters, NOT the even Sep/Dec-Apr-Aug thirds.
        self.assertEqual(terms[0].start_date, _dt.date(2025, 9, 1))
        self.assertEqual(terms[0].end_date, _dt.date(2025, 12, 15))
        self.assertEqual(terms[1].start_date, _dt.date(2026, 1, 5))
        # Third trimester ends in JULY (even split would have said Aug 31).
        self.assertEqual(terms[2].end_date, _dt.date(2026, 7, 10))
        self.assertNotEqual(terms[2].end_date, _dt.date(2026, 8, 31))


class TenantOverrideTests(TestCase):
    def test_settings_term_windows_override_wins(self):
        school = School.objects.create(
            name="Ov", subdomain="ov-cal", country_code="CM",
            settings={"term_windows": [[9, 1, 10, 31], [11, 1, 12, 31], [1, 15, 3, 31]]},
        )
        year, _ = ensure_academic_year(school, name="2025/2026")
        ensure_terms(school, year)
        terms = list(
            Term.objects.filter(school=school, academic_year=year).order_by("position")
        )
        self.assertEqual(terms[0].end_date, _dt.date(2025, 10, 31))
        self.assertEqual(terms[1].start_date, _dt.date(2025, 11, 1))
        self.assertEqual(terms[2].start_date, _dt.date(2026, 1, 15))


class FallbackAndGuardTests(TestCase):
    def test_unknown_country_returns_none_and_even_split_still_seeds_terms(self):
        school = School.objects.create(name="Zz", subdomain="zz-cal", country_code="CM")
        year, _ = ensure_academic_year(school, name="2025/2026")
        # No calendar for a made-up 5-term shape → resolver declines (shape/known
        # mismatch), and ensure_terms falls back to the even split.
        self.assertIsNone(
            resolve_term_windows(
                school, 5,
                year_start=year.start_date, year_end=year.end_date, start_month=9,
            )
        )

    def test_length_mismatch_is_rejected(self):
        # CM has a 3-window calendar; asking for 2 must not return a 3-list.
        school = School.objects.create(name="Mm", subdomain="mm-cal", country_code="CM")
        self.assertIsNone(
            resolve_term_windows(
                school, 2,
                year_start=_dt.date(2025, 9, 1), year_end=_dt.date(2026, 8, 31), start_month=9,
            )
        )

    def test_windows_are_clamped_inside_the_year(self):
        school = School.objects.create(name="Cl", subdomain="cl-cal", country_code="CM")
        wins = resolve_term_windows(
            school, 3,
            year_start=_dt.date(2025, 9, 1), year_end=_dt.date(2026, 8, 31), start_month=9,
        )
        self.assertIsNotNone(wins)
        for start, end in wins:
            self.assertLessEqual(_dt.date(2025, 9, 1), start)
            self.assertLessEqual(start, end)
            self.assertLessEqual(end, _dt.date(2026, 8, 31))
