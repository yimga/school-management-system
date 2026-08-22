"""Tests for scan_duplicate_dict_keys.

The two cases that matter most are the must-FIRE ones (a repeated key with
different values, and with identical values) and the live-tree seal, which is
what turns this from a script into a ratchet.
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import scan_duplicate_dict_keys as scanner  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]


def scan_source(source: str) -> list[dict]:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "sample.py"
        path.write_text(source, encoding="utf-8")
        return scanner.scan_file(path)


class DuplicateDetectionTests(unittest.TestCase):
    def test_shadowing_duplicate_is_a_finding(self):
        findings = scan_source('D = {\n    "a": 1,\n    "b": 2,\n    "a": 3,\n}\n')
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["key"], "a")
        self.assertFalse(findings[0]["identical"])
        self.assertEqual(findings[0]["lines"], [2, 4])
        # Python keeps the LAST occurrence.
        self.assertEqual(findings[0]["kept_line"], 4)

    def test_identical_repeat_is_a_finding_but_marked_identical(self):
        findings = scan_source('D = {\n    "a": 1,\n    "a": 1,\n}\n')
        self.assertEqual(len(findings), 1)
        self.assertTrue(findings[0]["identical"])

    def test_clean_dict_is_silent(self):
        self.assertEqual(scan_source('D = {"a": 1, "b": 2}\n'), [])

    def test_int_and_string_keys_do_not_collide(self):
        self.assertEqual(scan_source('D = {1: "x", "1": "y"}\n'), [])

    def test_true_and_one_collide_exactly_as_python_does(self):
        # {1: 'a', True: 'b'} really is a one-entry dict at runtime.
        source = 'D = {1: "a", True: "b"}\n'
        self.assertEqual(len(eval(source.split("=", 1)[1].strip())), 1)  # noqa: S307
        self.assertEqual(len(scan_source(source)), 1)

    def test_tuple_keys_are_compared_by_value(self):
        findings = scan_source('D = {\n    ("a", 1): "x",\n    ("a", 1): "y",\n}\n')
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["key"], ("a", 1))

    def test_non_constant_keys_are_skipped(self):
        self.assertEqual(scan_source("D = {k: 1, k: 2}\n"), [])

    def test_spread_does_not_crash_or_false_positive(self):
        self.assertEqual(scan_source('D = {**base, "a": 1}\n'), [])

    def test_nested_dicts_are_each_checked(self):
        findings = scan_source('D = {"outer": {"a": 1, "a": 2}}\n')
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["key"], "a")

    def test_separate_dicts_with_the_same_key_are_not_a_finding(self):
        self.assertEqual(scan_source('A = {"k": 1}\nB = {"k": 2}\n'), [])

    def test_unparseable_file_is_not_a_finding_here(self):
        # verify_python_files_parse owns that; reporting it twice buries the
        # report that actually explains the fix.
        self.assertEqual(scan_source("def broken(:\n"), [])


class LiveTreeTests(unittest.TestCase):
    def test_repo_scans_clean(self):
        """The ratchet. If this fails, a duplicate key reached the tree."""
        result = subprocess.run(
            [sys.executable, "scripts/scan_duplicate_dict_keys.py"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("PASS", result.stdout)

    def test_strict_flag_is_accepted(self):
        result = subprocess.run(
            [
                sys.executable,
                "scripts/scan_duplicate_dict_keys.py",
                "--strict",
                "scripts/scan_duplicate_dict_keys.py",
            ],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
