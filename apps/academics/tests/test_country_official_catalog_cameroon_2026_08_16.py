"""Cameroon real-data population — GCE Board subject codes + MINESEC calendar.

The country-data architecture (increments q-u) is leak-free; onboarding a country's
REAL data is now pure data population. This proves Cameroon is populated with
genuine, verifiable official data (not mnemonic placeholders), holding the honesty
rule:

* curated ``_NATIONAL_SUBJECT_CODES["CM"]`` returns the REAL Cameroon GCE Board
  numeric codes (Ordinary Level 05xx + Advanced-Level-only subjects 07xx), sourced
  from camgceb.org — verified across the official board site and two independent
  listings.
* curated ``_TERM_CALENDARS["CM"]`` follows the MINESEC 2025/2026 national
  school-year calendar boundaries.
* the shipped ``CM.json`` catalog is structurally valid, carries the same real
  codes, and imports idempotently into the shared profile.
* a subject the GCE Board does NOT code (e.g. Physical Education) still gets an
  honest mnemonic — never a fabricated numeric.
"""

from __future__ import annotations

import json
from pathlib import Path

from django.test import SimpleTestCase, TestCase

from apps.academics.country_subject_codes import _mnemonic, resolve_subject_code
from apps.academics.country_term_calendars import _TERM_CALENDARS
from apps.schools.models import School

_CM_JSON = (
    Path(__file__).resolve().parent.parent / "data" / "official_catalogs" / "CM.json"
)

# The real MINESEC 2025/2026 boundaries the curated default and CM.json both carry.
_CM_WINDOWS = [(9, 8, 12, 19), (1, 5, 4, 2), (4, 20, 7, 31)]


class CuratedCameroonRealCodesTests(SimpleTestCase):
    def test_ordinary_level_codes_are_real_gce_numeric(self):
        cm = School(country_code="CM")
        self.assertEqual(resolve_subject_code(cm, "Mathematics"), "0570")
        self.assertEqual(resolve_subject_code(cm, "English Language"), "0530")
        self.assertEqual(resolve_subject_code(cm, "Biology"), "0510")
        self.assertEqual(resolve_subject_code(cm, "French"), "0545")
        self.assertEqual(resolve_subject_code(cm, "Computer Science"), "0595")
        self.assertEqual(resolve_subject_code(cm, "Economics"), "0525")
        # case-insensitive + whitespace-trimmed
        self.assertEqual(resolve_subject_code(cm, "  human biology "), "0565")

    def test_advanced_level_only_subjects_carry_real_a_level_codes(self):
        cm = School(country_code="CM")
        self.assertEqual(resolve_subject_code(cm, "Further Mathematics"), "0775")
        self.assertEqual(resolve_subject_code(cm, "Philosophy"), "0790")
        self.assertEqual(
            resolve_subject_code(cm, "Information and Communication Technology"), "0796"
        )

    def test_uncoded_subject_gets_honest_mnemonic_not_a_fake_number(self):
        # The GCE Board does not code Physical Education — it must fall to the
        # mnemonic, never a fabricated numeric. Honesty rule.
        cm = School(country_code="CM")
        code = resolve_subject_code(cm, "Physical Education")
        self.assertEqual(code, _mnemonic("Physical Education"))
        self.assertFalse(code.isdigit(), "PE must not be given a fabricated numeric code")

    def test_curated_windows_follow_minesec_calendar(self):
        self.assertEqual(_TERM_CALENDARS["CM"], _CM_WINDOWS)
        # Both subsystems share the single national ministry calendar.
        self.assertEqual(_TERM_CALENDARS["CM-EN"], _CM_WINDOWS)
        self.assertEqual(_TERM_CALENDARS["CM-FR"], _CM_WINDOWS)


class ShippedCameroonCatalogFileTests(SimpleTestCase):
    def test_cm_json_exists_and_is_valid(self):
        from apps.academics.official_catalog import parse_catalog

        self.assertTrue(_CM_JSON.exists(), "CM.json must ship")
        raw = json.loads(_CM_JSON.read_text(encoding="utf-8"))
        parsed = parse_catalog(raw)
        self.assertEqual(parsed["country"], "CM")
        # Real GCE codes, stored as strings so leading zeros survive.
        self.assertEqual(parsed["subject_codes"]["mathematics"], "0570")
        self.assertEqual(parsed["subject_codes"]["english language"], "0530")
        self.assertEqual(parsed["subject_codes"]["further mathematics"], "0775")
        self.assertEqual(parsed["term_windows"], [[9, 8, 12, 19], [1, 5, 4, 2], [4, 20, 7, 31]])

    def test_cm_json_codes_all_numeric_leading_zero_preserved(self):
        raw = json.loads(_CM_JSON.read_text(encoding="utf-8"))
        for name, code in raw["subject_codes"].items():
            self.assertTrue(code.isdigit(), f"{name} code {code!r} must be numeric")
            self.assertEqual(len(code), 4, f"{name} GCE code {code!r} must be 4 digits")


class ImportCameroonCatalogTests(TestCase):
    def test_import_cm_json_applies_then_idempotent(self):
        from apps.academics.official_catalog import (
            _existing_country_profile,
            import_catalog,
            load_catalog_file,
        )

        parsed = load_catalog_file(_CM_JSON)
        first = import_catalog(parsed)
        self.assertIn(first["status"], ("applied", "unchanged"))
        # Real codes now live in the region-shared profile config.
        profile = _existing_country_profile("CM", "")
        self.assertIsNotNone(profile)
        self.assertEqual(profile.config["subject_codes"]["mathematics"], "0570")
        # Re-import changes nothing.
        second = import_catalog(parsed)
        self.assertEqual(second["status"], "unchanged")
        self.assertEqual(second["subject_codes_changed"], 0)
        self.assertEqual(second["term_windows_changed"], 0)
