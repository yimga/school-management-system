"""Increment (n) — national subject-code tables beyond Cameroon.

Increment (d) shipped Cameroon + a universal mnemonic fallback. This adds real
national code schemes: Kenya's KNEC/KCSE numeric codes, India's CBSE numeric
codes, and WAEC / NSC / GCSE / bac mnemonic sets (shared across Anglophone West
Africa and francophone countries). The mnemonic fallback still covers every
subject in every un-curated country, so no subject is ever left code-less.
"""

from __future__ import annotations

from django.test import SimpleTestCase

from apps.academics.country_subject_codes import resolve_subject_code
from apps.schools.models import School


class NationalNumericCodeTests(SimpleTestCase):
    def test_kenya_knec_numeric_codes(self):
        ke = School(country_code="KE")
        self.assertEqual(resolve_subject_code(ke, "English"), "101")
        self.assertEqual(resolve_subject_code(ke, "Mathematics"), "121")
        self.assertEqual(resolve_subject_code(ke, "Biology"), "231")
        self.assertEqual(resolve_subject_code(ke, "Business Studies"), "565")

    def test_india_cbse_numeric_codes(self):
        india = School(country_code="IN")
        self.assertEqual(resolve_subject_code(india, "Mathematics"), "041")
        self.assertEqual(resolve_subject_code(india, "Science"), "086")
        self.assertEqual(resolve_subject_code(india, "Computer Science"), "083")


class SharedMnemonicSetTests(SimpleTestCase):
    def test_waec_shared_across_anglophone_west_africa(self):
        for iso in ("NG", "GH", "LR", "SL", "GM"):
            school = School(country_code=iso)
            self.assertEqual(resolve_subject_code(school, "Mathematics"), "MTH", iso)
            self.assertEqual(resolve_subject_code(school, "English Language"), "ENG", iso)

    def test_francophone_bac_shared(self):
        for iso in ("FR", "CI", "SN", "ML", "GA", "CD", "MG"):
            school = School(country_code=iso)
            self.assertEqual(resolve_subject_code(school, "Mathématiques"), "MATH", iso)
            # bilingual entry: English resolves to the francophone Anglais code.
            self.assertEqual(resolve_subject_code(school, "English"), "ANGL", iso)

    def test_south_africa_and_uk_sets(self):
        za = School(country_code="ZA")
        self.assertEqual(resolve_subject_code(za, "Mathematical Literacy"), "MLIT")
        self.assertEqual(resolve_subject_code(za, "Life Sciences"), "LFSC")
        gb = School(country_code="GB")
        self.assertEqual(resolve_subject_code(gb, "Computer Science"), "COMP")


class FallbackAndBackwardCompatTests(SimpleTestCase):
    def test_cameroon_still_curated(self):
        cm = School(country_code="CM")
        self.assertEqual(resolve_subject_code(cm, "Mathematics"), "MATH")
        self.assertEqual(resolve_subject_code(cm, "French"), "FREN")

    def test_unknown_country_or_subject_uses_mnemonic(self):
        # un-curated country → mnemonic
        self.assertEqual(resolve_subject_code(School(country_code="XX"), "Welding Theory"), "WT")
        # curated country, un-listed subject → mnemonic
        self.assertEqual(resolve_subject_code(School(country_code="KE"), "Woodwork"), "WOOD")
