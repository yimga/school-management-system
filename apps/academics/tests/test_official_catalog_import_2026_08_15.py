"""Increment (s) — official-catalog import: pure data population, no deploy.

Proves the pump between a country's real official data (one JSON file) and the
region-shared ``EducationSystemProfile.config`` the resolver reads: parsing +
validation, additive/idempotent merge, a truly side-effect-free dry-run, the
shipped KE/IN real-code files, and the end-to-end path (import → a school in that
country resolves the override).
"""

from __future__ import annotations

from django.test import SimpleTestCase, TestCase

from apps.academics.official_catalog import (
    DEFAULT_CATALOG_DIR,
    OfficialCatalogError,
    _merge_into_config,
    import_catalog,
    load_catalog_file,
    parse_catalog,
)
from apps.academics.country_subject_codes import resolve_subject_code
from apps.schools.models import School


class ParseCatalogTests(SimpleTestCase):
    def test_valid_catalog_is_normalized(self):
        parsed = parse_catalog(
            {
                "country": "ke",
                "subject_codes": {"English": "101", "Mathematics": "121"},
                "term_windows": [[1, 5, 4, 5], [5, 2, 8, 5], [8, 28, 11, 25]],
            }
        )
        self.assertEqual(parsed["country"], "KE")
        self.assertEqual(parsed["subject_codes"]["english"], "101")   # key lowercased
        self.assertEqual(parsed["term_windows"][0], [1, 5, 4, 5])     # ints

    def test_missing_country_raises(self):
        with self.assertRaises(OfficialCatalogError):
            parse_catalog({"subject_codes": {"english": "101"}})

    def test_neither_field_raises(self):
        with self.assertRaises(OfficialCatalogError):
            parse_catalog({"country": "KE"})

    def test_bad_term_window_raises(self):
        with self.assertRaises(OfficialCatalogError):
            parse_catalog({"country": "KE", "term_windows": [[1, 2, 3]]})
        with self.assertRaises(OfficialCatalogError):
            parse_catalog({"country": "KE", "term_windows": [["x", 2, 3, 4]]})

    def test_subject_codes_must_be_object(self):
        with self.assertRaises(OfficialCatalogError):
            parse_catalog({"country": "KE", "subject_codes": ["english", "101"]})

    def test_blank_values_dropped(self):
        parsed = parse_catalog({"country": "KE", "subject_codes": {"a": "  ", "b": "X"}})
        self.assertEqual(parsed["subject_codes"], {"b": "X"})


class MergeTests(SimpleTestCase):
    def test_additive_preserves_unrelated_keys(self):
        merged, changes = _merge_into_config(
            {"grading": "keep-me", "subject_codes": {"english": "OLD"}},
            {"subject_codes": {"biology": "231"}},
        )
        self.assertEqual(merged["grading"], "keep-me")
        self.assertEqual(merged["subject_codes"]["english"], "OLD")   # untouched
        self.assertEqual(merged["subject_codes"]["biology"], "231")   # added
        self.assertEqual(changes["subject_codes"], 1)

    def test_idempotent_merge_reports_no_changes(self):
        base = {"subject_codes": {"english": "101"}}
        _merged, changes = _merge_into_config(base, {"subject_codes": {"english": "101"}})
        self.assertEqual(changes["subject_codes"], 0)

    def test_term_windows_replace_counts_once(self):
        merged, changes = _merge_into_config(
            {"term_windows": [[1, 2, 3, 4]]}, {"term_windows": [[5, 6, 7, 8]]}
        )
        self.assertEqual(merged["term_windows"], [[5, 6, 7, 8]])
        self.assertEqual(changes["term_windows"], 1)


class ShippedCatalogFilesTests(SimpleTestCase):
    def test_kenya_ships_real_knec_codes(self):
        parsed = load_catalog_file(DEFAULT_CATALOG_DIR / "KE.json")
        self.assertEqual(parsed["country"], "KE")
        self.assertEqual(parsed["subject_codes"]["english"], "101")
        self.assertEqual(parsed["subject_codes"]["mathematics"], "121")

    def test_india_ships_real_cbse_codes(self):
        parsed = load_catalog_file(DEFAULT_CATALOG_DIR / "IN.json")
        self.assertEqual(parsed["subject_codes"]["mathematics"], "041")
        self.assertEqual(parsed["subject_codes"]["science"], "086")


class ImportCatalogDbTests(TestCase):
    def test_import_writes_shared_profile_config_and_is_idempotent(self):
        parsed = parse_catalog(
            {"country": "KE", "subject_codes": {"robotics": "ROB-KE-1"}, "source": "test"}
        )
        first = import_catalog(parsed)
        self.assertEqual(first["status"], "applied")
        self.assertGreaterEqual(first["subject_codes_changed"], 1)

        # Re-import is idempotent.
        second = import_catalog(parsed)
        self.assertEqual(second["status"], "unchanged")
        self.assertEqual(second["subject_codes_changed"], 0)

    def test_dry_run_writes_nothing(self):
        parsed = parse_catalog({"country": "GH", "subject_codes": {"woodwork": "WW-GH"}})
        summary = import_catalog(parsed, dry_run=True)
        self.assertEqual(summary["status"], "dry-run")
        # A real apply afterward must still see it as brand-new (dry-run created no rows).
        applied = import_catalog(parsed)
        self.assertEqual(applied["status"], "applied")
        self.assertGreaterEqual(applied["subject_codes_changed"], 1)

    def test_shipped_kenya_import_lands_real_codes(self):
        summary = import_catalog(load_catalog_file(DEFAULT_CATALOG_DIR / "KE.json"))
        self.assertIn(summary["status"], ("applied", "unchanged"))
        from apps.academics.official_catalog import _existing_country_profile

        profile = _existing_country_profile("KE", "")
        self.assertIsNotNone(profile)
        self.assertEqual(profile.config["subject_codes"]["english"], "101")

    def test_end_to_end_school_resolves_imported_override(self):
        # Import a code that is NOT in the curated KE table, so a hit proves the
        # profile-override cascade layer (not the curated default) was read.
        from apps.siteconfig.education_profile_engine import ensure_region_for_country

        import_catalog(parse_catalog({"country": "KE", "subject_codes": {"robotics": "ROB-KE-1"}}))
        region = ensure_region_for_country("KE")
        school = School.objects.create(
            name="Nairobi Tech", subdomain="nbo-tech-s", country_code="KE", default_region=region
        )
        # Curated has no "robotics" → without the override this would be the mnemonic "ROBO".
        self.assertEqual(resolve_subject_code(school, "Robotics"), "ROB-KE-1")
