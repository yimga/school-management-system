"""Increment (e) — the per-country TVET/vocational trade catalog.

The platform shipped no trade catalog: a technical school landed with only a
"General" specialty and nowhere to place a student's course of study. These tests
pin: vocational schools get a country-appropriate trade set, general-ed schools
get NOTHING (no stray welding specialty), an uploaded trade list always wins, and
the globally-unique Department/Specialty codes never collide (the [:30]
truncation trap that broke UUID schools before).
"""

from __future__ import annotations

from django.test import TestCase

from apps.academics.country_trade_catalogs import resolve_trade_catalog
from apps.academics.models import Department, Specialty
from apps.academics.structure_provisioning import (
    _is_vocational_school,
    seed_country_trades,
)
from apps.schools.models import School


class VocationalGateTests(TestCase):
    def test_school_type_marker_reads_as_vocational(self):
        self.assertTrue(_is_vocational_school(School(settings={"school_type": "tvet"})))
        self.assertTrue(_is_vocational_school(School(settings={"school_type_raw": "Technical College"})))
        self.assertFalse(_is_vocational_school(School(settings={"school_type": "secondary"})))
        self.assertFalse(_is_vocational_school(School()))


class TradeCatalogResolveTests(TestCase):
    def test_cameroon_curated_and_generic_fallback(self):
        cm = resolve_trade_catalog(School(country_code="CM"))
        cm_trades = [t for _, trades in cm for t in trades]
        self.assertIn("Welding & Metal Fabrication", cm_trades)
        # unknown country still gets the universal generic set (never empty)
        xx = resolve_trade_catalog(School(country_code="XX"))
        self.assertTrue(xx)
        self.assertTrue(any("Welding" in t for _, trades in xx for t in trades))

    def test_tenant_override_wins(self):
        school = School(country_code="CM", settings={"trade_catalog": [["Auto", ["Panel Beating"]]]})
        cat = resolve_trade_catalog(school)
        self.assertEqual(cat, [("Auto", ["Panel Beating"])])


class SeedTradesTests(TestCase):
    def test_vocational_school_gets_trades_with_unique_codes(self):
        school = School.objects.create(
            name="TVET", subdomain="tvet-trades", country_code="CM",
            settings={"school_type": "tvet"},
        )
        result = seed_country_trades(school)
        self.assertGreater(result.get("created_specialties", 0), 0)
        self.assertGreater(result.get("created_departments", 0), 0)

        specs = Specialty.objects.filter(school=school)
        self.assertTrue(specs.filter(name="Welding & Metal Fabrication").exists())
        # Globally-unique codes must all be distinct (the [:30] truncation trap).
        codes = list(specs.values_list("code", flat=True))
        self.assertEqual(len(codes), len(set(codes)), "specialty codes must be unique")
        dept_codes = list(Department.objects.filter(school=school).values_list("code", flat=True))
        self.assertEqual(len(dept_codes), len(set(dept_codes)), "department codes must be unique")

    def test_general_ed_school_gets_no_trades(self):
        school = School.objects.create(
            name="Gen", subdomain="gen-notrade", country_code="CM",
            settings={"school_type": "secondary"},
        )
        result = seed_country_trades(school)
        self.assertEqual(result.get("skipped"), "not_vocational")
        self.assertEqual(Specialty.objects.filter(school=school).count(), 0)

    def test_uploaded_trades_are_never_overridden(self):
        school = School.objects.create(
            name="Up", subdomain="up-trade", country_code="CM",
            settings={"school_type": "tvet"},
        )
        dept = Department.objects.create(school=school, name="Eng", code=f"up-{str(school.id)[:6]}")
        Specialty.objects.create(school=school, department=dept, name="Boat Building", code=f"bb-{str(school.id)[:6]}")
        result = seed_country_trades(school)
        self.assertEqual(result.get("skipped"), "specialties_exist")
        self.assertEqual(Specialty.objects.filter(school=school).count(), 1)

    def test_idempotent_reseed(self):
        school = School.objects.create(
            name="Id", subdomain="id-trade", country_code="CM",
            settings={"school_type": "tvet"},
        )
        seed_country_trades(school)
        count1 = Specialty.objects.filter(school=school).count()
        # A second call finds the trades already present (by name) and adds none.
        seed_country_trades(school)
        self.assertEqual(Specialty.objects.filter(school=school).count(), count1)
