"""Audit upgrade — official-catalog import provenance + conflict-aware diffs.

Increment (s) imported a catalog but discarded its ``source`` (the audit trail) and
overwrote existing codes silently. This proves the closure:

* ``_merge_into_config`` reports added vs overwritten, with the exact old→new diffs.
* ``import_catalog`` persists a provenance record (source + when + counts) into
  ``config['catalog_provenance']`` on every applied import, capped and append-only.
* a dry-run surfaces the diffs and writes nothing.
* the management command prints the diffs + the ``--resync-codes`` follow-up.
"""

from __future__ import annotations

from io import StringIO

from django.core.management import call_command
from django.test import SimpleTestCase, TestCase

from apps.academics.official_catalog import (
    _merge_into_config,
    import_catalog,
    parse_catalog,
)


class MergeDiffTests(SimpleTestCase):
    def test_added_vs_overwritten_classification(self):
        _merged, changes = _merge_into_config(
            {"subject_codes": {"english": "101"}},
            {"subject_codes": {"english": "ENG-NEW", "biology": "231"}},
        )
        self.assertEqual(changes["subject_added"], 1)         # biology
        self.assertEqual(changes["subject_overwritten"], 1)   # english 101 -> ENG-NEW
        self.assertEqual(changes["subject_codes"], 2)
        kinds = {d["name"]: (d["kind"], d["old"], d["new"]) for d in changes["subject_diffs"]}
        self.assertEqual(kinds["english"], ("overwritten", "101", "ENG-NEW"))
        self.assertEqual(kinds["biology"], ("added", "", "231"))

    def test_unchanged_code_is_not_a_diff(self):
        _merged, changes = _merge_into_config(
            {"subject_codes": {"english": "101"}}, {"subject_codes": {"english": "101"}}
        )
        self.assertEqual(changes["subject_codes"], 0)
        self.assertEqual(changes["subject_diffs"], [])

    def test_term_window_diff_captured(self):
        _merged, changes = _merge_into_config(
            {"term_windows": [[1, 2, 3, 4]]}, {"term_windows": [[5, 6, 7, 8]]}
        )
        self.assertEqual(changes["term_window_diff"], {"old": [[1, 2, 3, 4]], "new": [[5, 6, 7, 8]]})


class ImportProvenanceTests(TestCase):
    def test_applied_import_records_provenance(self):
        from apps.academics.official_catalog import _existing_country_profile

        import_catalog(parse_catalog(
            {"country": "KE", "subject_codes": {"robotics": "ROB-1"}, "source": "KNEC 2024"}
        ))
        profile = _existing_country_profile("KE", "")
        self.assertIsNotNone(profile)
        log = profile.config.get("catalog_provenance")
        self.assertTrue(log)
        self.assertEqual(log[-1]["source"], "KNEC 2024")
        self.assertEqual(log[-1]["subject_codes_changed"], 1)
        self.assertIn("when", log[-1])

    def test_unchanged_reimport_does_not_append_provenance(self):
        from apps.academics.official_catalog import _existing_country_profile

        parsed = parse_catalog(
            {"country": "GH", "subject_codes": {"woodwork": "WW-1"}, "source": "S1"}
        )
        import_catalog(parsed)
        import_catalog(parsed)   # idempotent re-import
        profile = _existing_country_profile("GH", "")
        self.assertEqual(len(profile.config.get("catalog_provenance", [])), 1)

    def test_summary_exposes_overwrite_and_diffs(self):
        import_catalog(parse_catalog({"country": "TZ", "subject_codes": {"physics": "OLD"}}))
        summary = import_catalog(
            parse_catalog({"country": "TZ", "subject_codes": {"physics": "NEW"}, "source": "board"})
        )
        self.assertEqual(summary["subject_overwritten"], 1)
        self.assertEqual(summary["diffs"][0], {"name": "physics", "old": "OLD", "new": "NEW", "kind": "overwritten"})

    def test_dry_run_reports_diff_writes_nothing(self):
        from apps.academics.official_catalog import _existing_country_profile

        parsed = parse_catalog({"country": "UG", "subject_codes": {"agriculture": "AGR-UG"}})
        summary = import_catalog(parsed, dry_run=True)
        self.assertEqual(summary["status"], "dry-run")
        self.assertEqual(summary["subject_added"], 1)
        self.assertIsNone(_existing_country_profile("UG", ""))   # no rows created


class ImportCommandOutputTests(TestCase):
    def test_command_prints_resync_followup_when_codes_change(self):
        import json
        import tempfile
        from pathlib import Path

        tmp = Path(tempfile.mkdtemp())
        catalog = tmp / "ZM.json"
        catalog.write_text(
            json.dumps({"country": "ZM", "subject_codes": {"english": "ENG-ZM"}, "source": "ECZ"}),
            encoding="utf-8",
        )
        out = StringIO()
        call_command("import_country_official_catalog", "--file", str(catalog), stdout=out)
        text = out.getvalue()
        self.assertIn("backfill_country_baseline --resync-codes", text)
        self.assertIn("ENG-ZM", text)
