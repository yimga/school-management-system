"""Increment (d) — Subject.code + the national/country-standard code scheme.

Subjects had no code, so report cards / transcripts / gov exports carried bare
names. These tests pin: the curated country table returns official-style codes,
the mnemonic fallback covers any subject, seeding stamps codes, and the backfill
codes uploaded/pre-existing catalogs without ever overriding an admin's code.
"""

from __future__ import annotations

from django.test import TestCase

from apps.academics.country_subject_codes import _mnemonic, resolve_subject_code
from apps.academics.models import Subject
from apps.academics.structure_provisioning import (
    backfill_subject_codes,
    seed_country_subjects,
)
from apps.schools.models import School


class ResolveCodeTests(TestCase):
    def test_curated_cameroon_codes(self):
        # REAL Cameroon GCE Board Ordinary-Level codes (camgceb.org).
        cm = School(country_code="CM")
        self.assertEqual(resolve_subject_code(cm, "Mathematics"), "0570")
        self.assertEqual(resolve_subject_code(cm, "English Language"), "0530")
        self.assertEqual(resolve_subject_code(cm, "French"), "0545")
        # case-insensitive lookup
        self.assertEqual(resolve_subject_code(cm, "  biology "), "0510")
        # Advanced-Level-only subject (distinct name, real A/L code)
        self.assertEqual(resolve_subject_code(cm, "Further Mathematics"), "0775")

    def test_mnemonic_fallback_for_unknown_subject_or_country(self):
        # single word -> first four letters
        self.assertEqual(_mnemonic("Woodwork"), "WOOD")
        # multi-word -> initials
        self.assertEqual(_mnemonic("Welding Theory"), "WT")
        self.assertEqual(_mnemonic("Religious Moral Education"), "RME")
        # unknown country falls through to the mnemonic
        xx = School(country_code="XX")
        self.assertEqual(resolve_subject_code(xx, "Welding Theory"), "WT")

    def test_empty_name_is_empty_code(self):
        self.assertEqual(resolve_subject_code(School(country_code="CM"), ""), "")


class SeedAndBackfillTests(TestCase):
    def test_seeded_subjects_carry_codes(self):
        school = School.objects.create(name="Sc", subdomain="sc-code", country_code="CM")
        seed_country_subjects(school)
        subjects = Subject.objects.filter(school=school)
        self.assertGreater(subjects.count(), 0)
        # every seeded subject has a non-blank code
        self.assertFalse(subjects.filter(code="").exists(), "seeded subjects must all be coded")
        math = subjects.filter(name__icontains="math").first()
        if math is not None:
            self.assertTrue(math.code)

    def test_backfill_codes_uploaded_catalog_without_overriding(self):
        school = School.objects.create(name="Up", subdomain="up-code", country_code="CM")
        blank = Subject.objects.create(school=school, name="Welding Theory")  # code=""
        pinned = Subject.objects.create(school=school, name="Physics", code="ADMIN-SET")

        result = backfill_subject_codes(school)
        self.assertGreaterEqual(result.get("coded_subjects", 0), 1)

        blank.refresh_from_db()
        pinned.refresh_from_db()
        self.assertEqual(blank.code, "WT")           # backfilled from the mnemonic
        self.assertEqual(pinned.code, "ADMIN-SET")   # admin's explicit code untouched

    def test_backfill_is_idempotent(self):
        school = School.objects.create(name="Id", subdomain="id-code", country_code="CM")
        Subject.objects.create(school=school, name="History")
        backfill_subject_codes(school)
        second = backfill_subject_codes(school)
        # nothing left blank to code on the second pass
        self.assertEqual(second.get("coded_subjects", 0), 0)
        # History resolves to the REAL Cameroon GCE Board code (0560), not a mnemonic.
        self.assertEqual(Subject.objects.get(school=school, name="History").code, "0560")
