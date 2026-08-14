"""Increment (k) — global academic-calendar coverage + the RegionConfig shape keystone.

``country_calendar_shape`` derives ``(start_month, term_count)`` from the SAME
curated windows the term seeder uses, and ``ensure_region_for_country`` now seeds a
fresh region from it. So every non-standard-calendar country (East-Africa January,
2-semester, 4-term) lands on a region whose shape AGREES with its term-date
calendar, instead of the blunt hemisphere default (Sep north / Jan south, 3 terms)
that used to leave those calendars silently unused (the alignment guard declined
them). These tests pin: the shape invariant across every curated country; the
representative shapes per region; that a fresh region is created with the curated
shape; and that a school in a previously-"dead-calendar" country now lands on its
REAL term windows end-to-end (not the even split).
"""

from __future__ import annotations

import datetime as _dt

from django.test import TestCase

from apps.academics.country_term_calendars import (
    _TERM_CALENDARS,
    country_calendar_shape,
)
from apps.academics.models import Term
from apps.academics.structure_provisioning import ensure_academic_year, ensure_terms
from apps.schools.models import School


class CalendarShapeInvariantTests(TestCase):
    def test_shape_is_first_window_month_and_length_for_every_country(self):
        # The keystone invariant: a region seeded from country_calendar_shape can
        # NEVER disagree with its own term windows, because the shape IS derived
        # from those windows (first-term month + count).
        for key, windows in _TERM_CALENDARS.items():
            if "-" in key:  # subsystem specializations share the bare-country shape
                continue
            shape = country_calendar_shape(key)
            self.assertIsNotNone(shape, f"{key} should resolve a shape")
            self.assertEqual(shape, (windows[0][0], len(windows)), f"{key} shape")

    def test_representative_shapes_across_all_regions(self):
        cases = {
            # West/Central Africa
            "CM": (9, 3), "NG": (9, 3), "SN": (10, 3), "MG": (10, 3),
            # East / Southern Africa
            "KE": (1, 3), "TZ": (1, 3), "UG": (2, 3), "ZA": (1, 4), "AO": (2, 3),
            # North Africa / MENA
            "EG": (9, 2), "DZ": (9, 3), "SA": (8, 3), "TR": (9, 2),
            # Europe
            "GB": (9, 3), "FR": (9, 3), "DE": (9, 2), "NL": (8, 2), "RU": (9, 4),
            # Americas
            "US": (8, 2), "CA": (9, 2), "BR": (2, 2), "AR": (3, 2), "CO": (1, 2),
            # Asia / Oceania
            "IN": (4, 2), "JP": (4, 3), "KR": (3, 2), "SG": (1, 4), "AU": (1, 4),
        }
        for iso, expected in cases.items():
            self.assertEqual(country_calendar_shape(iso), expected, iso)

    def test_unknown_or_blank_country_returns_none(self):
        self.assertIsNone(country_calendar_shape("XX"))
        self.assertIsNone(country_calendar_shape(""))
        self.assertIsNone(country_calendar_shape(None))  # type: ignore[arg-type]

    def test_alpha3_input_is_accepted_when_pycountry_available(self):
        try:
            import pycountry  # noqa: F401
        except Exception:  # pragma: no cover — dependency optional in some envs
            self.skipTest("pycountry not installed; alpha-3 conversion unavailable")
        self.assertEqual(country_calendar_shape("TZA"), (1, 3))
        self.assertEqual(country_calendar_shape("BRA"), (2, 2))
        self.assertEqual(country_calendar_shape("ZAF"), (1, 4))
        # MDG must map to MG (Madagascar), not a naive "MD" truncation.
        self.assertEqual(country_calendar_shape("MDG"), (10, 3))


class RegionShapeSeededFromCalendarTests(TestCase):
    """The fresh-region create path takes its shape from the curated calendar."""

    def _ensure_region(self, iso):
        from apps.siteconfig.education_profile_engine import ensure_region_for_country

        return ensure_region_for_country(iso)

    def test_tanzania_region_gets_january_three_terms_not_hemisphere_default(self):
        region = self._ensure_region("TZ")
        self.assertIsNotNone(region)
        # Old behaviour: TZ is not in the southern-hemisphere set, so it defaulted
        # to a September start with 3 terms — mis-aligned with its January calendar.
        self.assertEqual(region.academic_year_start_month, 1)
        self.assertEqual(region.term_count_per_year, 3)

    def test_south_africa_region_gets_four_terms(self):
        region = self._ensure_region("ZA")
        self.assertIsNotNone(region)
        self.assertEqual(region.academic_year_start_month, 1)
        self.assertEqual(region.term_count_per_year, 4)  # was 3 under the default

    def test_brazil_region_gets_february_two_semesters(self):
        region = self._ensure_region("BR")
        self.assertIsNotNone(region)
        self.assertEqual(region.academic_year_start_month, 2)
        self.assertEqual(region.term_count_per_year, 2)


class EndToEndRealWindowsTests(TestCase):
    """A school in a previously dead-calendar country now lands on REAL windows."""

    def test_tanzania_school_terms_land_on_real_january_windows(self):
        school = School.objects.create(name="TZsch", subdomain="tz-cal", country_code="TZ")
        year, _ = ensure_academic_year(school, name="2025/2026")
        # Country-aware year now starts in January for Tanzania.
        self.assertEqual(year.start_date.month, 1)
        ensure_terms(school, year)
        terms = list(
            Term.objects.filter(school=school, academic_year=year).order_by("position")
        )
        self.assertEqual(len(terms), 3)
        # Real TZ windows [(1,8,4,5),(4,20,6,25),(7,10,12,5)] — NOT an even split
        # that would put term 1 ending in April at the 4-month boundary anyway, but
        # the third term ends in December, which the Jan-start even split (Jan/May/
        # Sep thirds) would NOT produce ending on Dec 5.
        self.assertEqual(terms[0].start_date, _dt.date(2025, 1, 8))
        self.assertEqual(terms[2].end_date, _dt.date(2025, 12, 5))

    def test_south_africa_school_gets_four_real_terms(self):
        school = School.objects.create(name="ZAsch", subdomain="za-cal", country_code="ZA")
        year, _ = ensure_academic_year(school, name="2025")
        self.assertEqual(year.start_date.month, 1)
        ensure_terms(school, year)
        terms = list(
            Term.objects.filter(school=school, academic_year=year).order_by("position")
        )
        # Four terms — the 4-term calendar was previously rejected because the
        # region said 3, so it collapsed to a 3-way even split.
        self.assertEqual(len(terms), 4)
        self.assertEqual(terms[0].start_date, _dt.date(2025, 1, 15))
        self.assertEqual(terms[3].end_date, _dt.date(2025, 12, 11))

    def test_senegal_school_starts_in_october(self):
        school = School.objects.create(name="SNsch", subdomain="sn-cal", country_code="SN")
        year, _ = ensure_academic_year(school, name="2025/2026")
        self.assertEqual(year.start_date.month, 10)
        ensure_terms(school, year)
        terms = list(
            Term.objects.filter(school=school, academic_year=year).order_by("position")
        )
        self.assertEqual(len(terms), 3)
        self.assertEqual(terms[0].start_date, _dt.date(2025, 10, 1))


class BackfillMigrationLogicTests(TestCase):
    """The 0210 backfill corrects a wrong-shape region but never touches an
    explicitly-non-default one (curated exception or admin edit)."""

    def _run_backfill(self):
        import importlib

        from django.apps import apps as django_apps

        mod = importlib.import_module(
            "apps.siteconfig.migrations.0210_seed_region_academic_calendars"
        )
        mod.seed_region_academic_calendars(django_apps, None)

    def test_wrong_default_shape_is_corrected(self):
        from apps.siteconfig.models_platform_catalog import RegionConfig

        # A Tanzania region left on the old hemisphere default (Sep, 3 terms).
        RegionConfig.objects.filter(code="TZA").delete()
        RegionConfig.objects.create(
            code="TZA", name="Tanzania", academic_year_start_month=9, term_count_per_year=3,
        )
        self._run_backfill()
        region = RegionConfig.objects.get(code="TZA")
        self.assertEqual(region.academic_year_start_month, 1)
        self.assertEqual(region.term_count_per_year, 3)

    def test_curated_exception_two_semester_is_left_untouched(self):
        from apps.siteconfig.models_platform_catalog import RegionConfig

        # USA seeded 8/2 by migration 0090 — term_count 2 is not the default, so the
        # backfill must skip it entirely (never rewrite to something else).
        region, _ = RegionConfig.objects.get_or_create(
            code="USA",
            defaults={"name": "United States", "academic_year_start_month": 8, "term_count_per_year": 2},
        )
        region.academic_year_start_month = 8
        region.term_count_per_year = 2
        region.save(update_fields=["academic_year_start_month", "term_count_per_year"])
        self._run_backfill()
        region.refresh_from_db()
        self.assertEqual(region.academic_year_start_month, 8)
        self.assertEqual(region.term_count_per_year, 2)

    def test_admin_edited_febstart_is_left_untouched(self):
        from apps.siteconfig.models_platform_catalog import RegionConfig

        # Uganda seeded 2/3 — start month 2 is not a hemisphere default, so a
        # curated/edited non-{1,9} start is preserved.
        RegionConfig.objects.filter(code="UGA").delete()
        RegionConfig.objects.create(
            code="UGA", name="Uganda", academic_year_start_month=2, term_count_per_year=3,
        )
        self._run_backfill()
        region = RegionConfig.objects.get(code="UGA")
        self.assertEqual(region.academic_year_start_month, 2)
        self.assertEqual(region.term_count_per_year, 3)
