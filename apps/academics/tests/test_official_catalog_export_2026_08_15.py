"""Increment (t) — export curated defaults to an editable catalog template.

The other end of the demand-driven loop: proves build_catalog_template pre-fills a
country's real subject taxonomy + representative windows, round-trips through
parse_catalog / import_catalog (export -> fill -> import), and the management
command writes a valid, importable file. No fabrication — exported codes are the
curated mnemonics (or real KE/IN codes) an operator then replaces.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from django.core.management import call_command
from django.test import SimpleTestCase, TestCase

from apps.academics.official_catalog import (
    OfficialCatalogError,
    build_catalog_template,
    curated_countries,
    import_catalog,
    parse_catalog,
    serialize_catalog,
)


class BuildTemplateTests(SimpleTestCase):
    def test_kenya_template_carries_real_knec_codes(self):
        t = build_catalog_template("KE")
        self.assertEqual(t["country"], "KE")
        self.assertEqual(t["subject_codes"]["english"], "101")
        self.assertTrue(t["term_windows"])
        self.assertIn("REPRESENTATIVE", t["notes"])

    def test_alpha3_input_normalizes_to_alpha2(self):
        self.assertEqual(build_catalog_template("CMR")["country"], "CM")

    def test_unknown_country_raises(self):
        with self.assertRaises(OfficialCatalogError):
            build_catalog_template("ZZ")

    def test_curated_countries_are_clean_alpha2(self):
        countries = curated_countries()
        self.assertIn("KE", countries)
        self.assertIn("IN", countries)
        self.assertIn("CM", countries)
        self.assertTrue(all(len(c) == 2 for c in countries))


class RoundTripTests(SimpleTestCase):
    def test_template_round_trips_through_parse(self):
        parsed = parse_catalog(build_catalog_template("KE"))
        self.assertEqual(parsed["country"], "KE")
        self.assertEqual(parsed["subject_codes"]["english"], "101")

    def test_serialize_is_valid_json(self):
        text = serialize_catalog(build_catalog_template("IN"))
        reloaded = json.loads(text)
        self.assertEqual(reloaded["country"], "IN")
        self.assertEqual(reloaded["subject_codes"]["mathematics"], "041")


class CommandTests(SimpleTestCase):
    def test_command_writes_importable_file(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "KE.json"
            call_command("export_country_catalog_template", country="KE", out=str(out))
            self.assertTrue(out.exists())
            # The written file parses as a valid catalog.
            parsed = parse_catalog(json.loads(out.read_text(encoding="utf-8")))
            self.assertEqual(parsed["country"], "KE")

    def test_all_writes_many_templates(self):
        with tempfile.TemporaryDirectory() as d:
            call_command("export_country_catalog_template", all=True, out_dir=d)
            files = list(Path(d).glob("*.json"))
            self.assertGreater(len(files), 20)  # all sovereign countries have windows


class ExportImportRoundTripDbTests(TestCase):
    def test_built_template_imports_into_profile_config(self):
        summary = import_catalog(parse_catalog(build_catalog_template("KE")))
        self.assertIn(summary["status"], ("applied", "unchanged"))
        from apps.academics.official_catalog import _existing_country_profile

        profile = _existing_country_profile("KE", "")
        self.assertIsNotNone(profile)
        self.assertEqual(profile.config["subject_codes"]["english"], "101")
