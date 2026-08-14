"""Increment (a) — the single country-appropriate baseline provisioner.

``provision_country_baseline`` is the ONE function both doors a school enters
through (self-service onboarding + Migration-Cloud gap-fill) now converge on, so
a school gets the same country-aware minimum baseline whichever way it arrived.

These tests pin the three things the foundation had to get right:

* the year WINDOW is country-aware (the bug: migration hardcoded a Sept→Aug year
  for every country, so a southern-hemisphere school got the wrong calendar);
* a blank/unlinked region is back-filled from ``country_code`` before
  provisioning (else the school silently drops to a generic 3-term structure);
* the whole baseline (year + terms + grading + General dept/specialty) lands and
  is idempotent on re-run.
"""

from __future__ import annotations

from django.test import TestCase

from apps.academics.models import AcademicYear, Department, Specialty, Term
from apps.academics.structure_provisioning import (
    ensure_academic_year,
    ensure_school_region,
    provision_country_baseline,
)
from apps.schools.models import School


class CountryAwareYearTests(TestCase):
    def test_cameroon_gets_a_september_start_year_and_three_terms(self):
        school = School.objects.create(name="CM Base", subdomain="cm-base", country_code="CM")
        summary = provision_country_baseline(school)

        year = AcademicYear.objects.filter(school=school, is_active=True).first()
        self.assertIsNotNone(year, "an active academic year should be minted")
        # Cameroon starts its year in September (RegionConfig CMR).
        self.assertEqual(year.start_date.month, 9)
        # A full year window ends the day before the next year would start.
        self.assertEqual(year.end_date.month, 8)

        terms = list(Term.objects.filter(school=school, academic_year=year))
        self.assertEqual(len(terms), 3, "Cameroon = 3 trimesters")
        self.assertEqual(
            Term.objects.filter(school=school, academic_year=year, is_active=True).count(),
            1,
            "exactly one term must be active (marks entry 403s without one)",
        )
        self.assertEqual(summary.get("terms", {}).get("term_count"), 3)

    def test_southern_hemisphere_year_is_not_hardcoded_september(self):
        # The bug this closes: the migration path minted a Sept→Aug year for EVERY
        # country. An Australian school starts its year in Jan/Feb — proving the
        # start month now comes from the country's RegionConfig, not a constant.
        school = School.objects.create(name="AU Base", subdomain="au-base", country_code="AU")
        year, created = ensure_academic_year(school)
        self.assertTrue(created)
        self.assertIn(
            year.start_date.month, (1, 2),
            f"southern-hemisphere year should start Jan/Feb, got month {year.start_date.month}",
        )

    def test_named_year_window_is_derived_from_the_name(self):
        school = School.objects.create(name="Nm", subdomain="nm-base", country_code="CM")
        year, created = ensure_academic_year(school, name="2027/2028")
        self.assertTrue(created)
        self.assertEqual(year.name, "2027/2028")
        self.assertEqual(year.start_date.year, 2027)
        self.assertEqual(year.start_date.month, 9)  # CM start month, from the name's first year


class RegionFallbackTests(TestCase):
    def test_blank_region_is_backfilled_from_country_code(self):
        school = School.objects.create(name="RF", subdomain="rf-base", country_code="CM")
        # Simulate a tenant whose region link was never set (the migration gap).
        School.objects.filter(pk=school.pk).update(default_region=None)
        school.refresh_from_db()
        self.assertIsNone(school.default_region_id)

        region = ensure_school_region(school)
        self.assertIsNotNone(region, "a region should be resolved from country_code=CM")
        school.refresh_from_db()
        self.assertIsNotNone(school.default_region_id, "region should be persisted on the school")

    def test_no_country_returns_none_not_error(self):
        school = School.objects.create(name="NC", subdomain="nc-base")
        School.objects.filter(pk=school.pk).update(default_region=None, country_code="")
        school.refresh_from_db()
        self.assertIsNone(ensure_school_region(school))  # graceful, no exception


class BaselineCompletenessTests(TestCase):
    def test_baseline_seeds_defaults_and_grading_and_is_idempotent(self):
        from apps.evals.models import GradingScale

        school = School.objects.create(name="Full", subdomain="full-base", country_code="CM")
        first = provision_country_baseline(school)

        # General department + specialty (the fee-plan / subject-assignment anchors).
        self.assertTrue(Department.objects.filter(school=school, name="General").exists())
        self.assertTrue(Specialty.objects.filter(school=school, name="General").exists())
        self.assertTrue(first.get("defaults", {}).get("general_specialty"))
        # Country grading scale row.
        self.assertTrue(GradingScale.objects.filter(school=school).exists())
        self.assertTrue(first.get("grading_scale"))

        year_count = AcademicYear.objects.filter(school=school).count()
        term_count = Term.objects.filter(school=school).count()

        # Re-run: nothing new (every step idempotent).
        provision_country_baseline(school)
        self.assertEqual(AcademicYear.objects.filter(school=school).count(), year_count)
        self.assertEqual(Term.objects.filter(school=school).count(), term_count)

    def test_null_school_is_a_graceful_skip(self):
        self.assertEqual(provision_country_baseline(None), {"skipped": "no_school"})
