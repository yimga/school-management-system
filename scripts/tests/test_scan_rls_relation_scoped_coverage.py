"""Coverage for ``scan_rls_relation_scoped_coverage``.

Needs Django (the app registry is what answers "does this model reach a School"),
so this boots it once, like the other registry-backed gate tests.

The calibration tests matter more than usual here. This gate exists because a
sibling gate reported a truthful ZERO to a question that missed the real problem,
so a number from THIS scan is worth nothing unless the scan is shown to see
tables it should and ignore tables it should not.
"""

from __future__ import annotations

import importlib.util
import json
import os
import pathlib
import sys
import unittest

SCRIPTS_DIR = pathlib.Path(__file__).resolve().parent.parent
REPO_ROOT = SCRIPTS_DIR.parent


def _load():
    spec = importlib.util.spec_from_file_location(
        "scan_rls_relation_scoped_coverage",
        SCRIPTS_DIR / "scan_rls_relation_scoped_coverage.py",
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class RlsRelationScopedCoverageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.chdir(REPO_ROOT)
        sys.path.insert(0, str(REPO_ROOT))
        cls.mod = _load()
        cls.mod._bootstrap_django()
        cls.findings = cls.mod.scan()

    def test_it_reads_the_fk_scoped_dict_shape(self):
        """The correction that made the count true.

        feedback/0010, communication/0031 and school_events/0004 enumerate their
        tables as dict KEYS. Without reading that shape the scan reports six
        already-protected tables as gaps.
        """
        tables = self.mod._fk_scoped_tables()
        for table in (
            "feedback_feedbackcomment",
            "school_events_eventregistration",
            "communication_threadmessageattachment",
        ):
            self.assertIn(table, tables, table)

    def test_tables_protected_by_an_fk_scoped_migration_are_not_findings(self):
        reported = {f["table"] for f in self.findings}
        for table in (
            "feedback_feedbackcomment",
            "feedback_feedbackattachment",
            "school_events_eventregistration",
            "school_events_eventtickettier",
            "school_events_eventsponsorcommitment",
        ):
            self.assertNotIn(table, reported, f"{table} IS protected; do not report it")

    def test_it_does_not_double_report_what_the_sibling_gate_owns(self):
        """A model with a literal `school` field belongs to the other scan."""
        from django.apps import apps as django_apps

        for f in self.findings:
            model = django_apps.get_model(f["model"])
            names = {fld.name for fld in model._meta.get_fields()}
            self.assertNotIn("school", names, f["model"])

    def test_every_finding_names_the_relation_it_travels(self):
        for f in self.findings:
            self.assertTrue(f["via"], f)

    def test_it_actually_found_something(self):
        # Calibration: a scan reporting zero here would look like good news and
        # would in fact mean the walk is broken. That mistake is why this gate exists.
        self.assertGreater(len(self.findings), 20, len(self.findings))

    def test_the_live_tree_matches_its_baseline(self):
        baseline = json.loads(
            (REPO_ROOT / "var" / "security-audit-baseline-rls-relation-coverage.json")
            .read_text(encoding="utf-8")
        )["finding_count"]
        self.assertLessEqual(
            len(self.findings),
            baseline,
            "a new tenant table reaches its school through a relation and has no "
            "RLS policy",
        )


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
