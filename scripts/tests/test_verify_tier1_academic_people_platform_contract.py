"""Tests for verify_tier1_academic_people_platform_contract.py."""

from __future__ import annotations

import io
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import verify_tier1_academic_people_platform_contract as gate  # noqa: E402


class TempContractTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self._real_root = gate.REPO_ROOT
        gate.REPO_ROOT = self.root

    def tearDown(self):
        gate.REPO_ROOT = self._real_root
        self._tmp.cleanup()

    def _write(self, rel: str, text: str) -> None:
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        with io.open(path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)

    def test_missing_file_is_a_finding(self):
        findings = gate.scan()
        self.assertTrue(any(f["reason"] == "file_missing" for f in findings))

    def test_mutation_on_lander_is_caught(self):
        self._write(
            "apps/migration_cloud/landers/academics_lander.py",
            "# category support removed\n",
        )
        findings = gate.scan()
        self.assertTrue(
            any(
                f["field"] == "Subject.category.lander" and "missing_needle" in f["reason"]
                for f in findings
            )
        )


class LiveTreeTests(unittest.TestCase):
    def test_clean_tree_passes(self):
        findings = gate.scan()
        self.assertEqual(findings, [], findings)

    def test_main_exits_zero_on_clean_tree(self):
        self.assertEqual(gate.main([]), 0)


if __name__ == "__main__":
    unittest.main()
