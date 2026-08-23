"""Coverage for ``scan_rls_null_school_arm``.

Needs Django: nullability comes from the live model registry, which is the whole
point -- a hardcoded table list is what let this class spread across 14 apps.
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
        "scan_rls_null_school_arm", SCRIPTS_DIR / "scan_rls_null_school_arm.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class RlsNullSchoolArmTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.chdir(REPO_ROOT)
        sys.path.insert(0, str(REPO_ROOT))
        cls.mod = _load()
        cls.mod._bootstrap_django()
        cls.findings = cls.mod.scan()

    def test_it_reads_clauses_out_of_migrations(self):
        # Calibration: no clauses discovered would make every assertion vacuous
        # and would report a comfortable zero.
        self.assertTrue(self.mod._winning_clauses("policies"))

    def test_the_app_that_already_fixed_this_is_clean(self):
        """apps/policies corrected its three hybrid tables today.

        If this ever reports a policies table, the detector is reading the wrong
        clause -- which is the failure mode that matters most here.
        """
        self.assertEqual([f for f in self.findings if f["app"] == "policies"], [])

    def test_every_finding_really_has_a_nullable_school(self):
        from django.apps import apps as django_apps

        for f in self.findings:
            field = django_apps.get_model(f["model"])._meta.get_field("school")
            self.assertTrue(field.null, f["model"])

    def test_every_finding_really_lacks_the_arm(self):
        for f in self.findings:
            clause = self.mod._winning_clauses(f["app"])[f["table"]]
            self.assertNotIn(self.mod.NULL_ARM, clause, f["model"])

    def test_it_found_something(self):
        self.assertGreater(len(self.findings), 5, len(self.findings))

    def test_the_live_tree_matches_its_baseline(self):
        baseline = json.loads(
            (REPO_ROOT / "var" / "security-audit-baseline-rls-null-school-arm.json")
            .read_text(encoding="utf-8")
        )["finding_count"]
        self.assertLessEqual(len(self.findings), baseline)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
