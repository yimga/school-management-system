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

from apps.academics.country_term_calendars import (
    _TERM_CALENDARS,
    resolve_term_windows,
)
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
        # Assert against the CURATED table rather than literals: these dates are
        # real MINESEC boundaries and get refreshed, and hardcoding a copy of them
        # here is what left this test red from b2cc95e57 onward.
        curated = _TERM_CALENDARS["CM"]
        self.assertEqual(len(curated), 3, "fixture drift: CM is no longer 3 terms")
        self.assertEqual(
            (terms[0].start_date.month, terms[0].start_date.day),
            (curated[0][0], curated[0][1]),
        )
        self.assertEqual(
            (terms[0].end_date.month, terms[0].end_date.day),
            (curated[0][2], curated[0][3]),
        )
        self.assertEqual(
            (terms[1].start_date.month, terms[1].start_date.day),
            (curated[1][0], curated[1][1]),
        )
        # The point of the whole feature: term 1 starts in September of the FIRST
        # calendar year and the third trimester ends in JULY. An even 12//3 split
        # would have ended it on Aug 31, which is the bug this pins.
        self.assertEqual(terms[0].start_date.year, 2025)
        self.assertEqual(terms[2].end_date.year, 2026)
        self.assertEqual(terms[2].end_date.month, 7)
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


class AlignmentAndWalkAnchorTests(TestCase):
    """Regression for the collapse/scramble bug: a January-start calendar (Kenya)
    anchored on a September start month produced single-day / out-of-order terms."""

    def test_aligned_january_calendar_is_ordered_and_not_collapsed(self):
        school = School(country_code="KE")  # unsaved: resolver reads country_code only
        wins = resolve_term_windows(
            school, 3,
            year_start=_dt.date(2025, 1, 1), year_end=_dt.date(2025, 12, 31), start_month=1,
        )
        self.assertIsNotNone(wins, "an aligned Jan-start calendar should apply")
        for start, end in wins:
            self.assertLess(start, end, "no term may collapse to a single day")
        # strictly chronological across terms
        self.assertLess(wins[0][1], wins[1][0])
        self.assertLess(wins[1][1], wins[2][0])
        self.assertEqual(wins[0][0], _dt.date(2025, 1, 5))
        self.assertEqual(wins[2][1], _dt.date(2025, 11, 25))

    def test_misaligned_calendar_falls_back_to_even_split(self):
        # Kenya's calendar starts January; a Sept-start academic year does not
        # match, so the guard declines (caller uses the even split that fits).
        school = School(country_code="KE")
        self.assertIsNone(
            resolve_term_windows(
                school, 3,
                year_start=_dt.date(2025, 9, 1), year_end=_dt.date(2026, 8, 31), start_month=9,
            )
        )

    def test_cameroon_still_aligned_and_correct(self):
        school = School(country_code="CM")
        wins = resolve_term_windows(
            school, 3,
            year_start=_dt.date(2025, 9, 1), year_end=_dt.date(2026, 8, 31), start_month=9,
        )
        self.assertIsNotNone(wins)
        curated = _TERM_CALENDARS["CM"]
        self.assertEqual(
            (wins[0][0].month, wins[0][0].day), (curated[0][0], curated[0][1])
        )
        self.assertEqual(
            (wins[1][0].month, wins[1][0].day), (curated[1][0], curated[1][1])
        )
        # The walk anchor is what this class exists for: term 1 sits in the first
        # calendar year, terms 2 and 3 have walked into the next one, in order.
        self.assertEqual(wins[0][0].year, 2025)
        self.assertEqual(wins[1][0].year, 2026)
        self.assertEqual(wins[2][1].year, 2026)
        self.assertEqual(wins[2][1].month, 7)
        self.assertLess(wins[0][1], wins[1][0])
        self.assertLess(wins[1][1], wins[2][0])


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
