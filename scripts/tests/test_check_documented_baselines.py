"""Unit tests for scripts/check_documented_baselines.py.

Tests the pure-logic surface: CLAUDE.md table parsing + JSON baseline
reading + drift detection. The subprocess re-run path (--full) and
JSON output formatting are exercised by the verify_platform_readiness
integration tests, not here.
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


def _load_module():
    """Import the script as a module without running main()."""
    repo_root = Path(__file__).resolve().parents[2]
    script_path = repo_root / "scripts" / "check_documented_baselines.py"
    spec = importlib.util.spec_from_file_location(
        "check_documented_baselines", script_path
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["check_documented_baselines"] = module
    spec.loader.exec_module(module)
    return module


class ClaudeMdParserTests(unittest.TestCase):
    def setUp(self):
        self.mod = _load_module()

    def _write_temp_claude(self, content: str) -> Path:
        # mkstemp returns (fd, path); closing the fd before unlink avoids
        # the Windows "file in use" PermissionError on tearDown.
        fd, name = tempfile.mkstemp(suffix=".md")
        os.close(fd)
        path = Path(name)
        path.write_text(content, encoding="utf-8")
        return path

    def test_parses_basic_integer_baseline(self):
        content = (
            "| Scanner | Baseline | Workflow | Rule |\n"
            "|---|---|---|---|\n"
            "| `scan_ai_gateway_boundary.py` | 0 | wf | rule |\n"
        )
        path = self._write_temp_claude(content)
        try:
            rows = self.mod.parse_claude_md(path)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0].scanner, "scan_ai_gateway_boundary.py")
            self.assertEqual(rows[0].documented, 0)
        finally:
            path.unlink(missing_ok=True)

    def test_parses_bold_integer_baseline(self):
        content = "| `scan_role_strings.py` | **272** (was 367 ...) | wf | rule |\n"
        path = self._write_temp_claude(content)
        try:
            rows = self.mod.parse_claude_md(path)
            self.assertEqual(rows[0].documented, 272)
        finally:
            path.unlink(missing_ok=True)

    def test_parses_integer_with_trailing_annotation(self):
        content = "| `scan_tenant_queryset_safety.py` | 734 (v2.48+L1a; was 742) | wf | rule |\n"
        path = self._write_temp_claude(content)
        try:
            rows = self.mod.parse_claude_md(path)
            self.assertEqual(rows[0].documented, 734)
        finally:
            path.unlink(missing_ok=True)

    def test_parses_n_a_baseline_as_none(self):
        content = "| `check_real_migration_drift.py` | n/a (filter, not baseline) | wf | rule |\n"
        path = self._write_temp_claude(content)
        try:
            rows = self.mod.parse_claude_md(path)
            # "n/a" should parse as None for documented value.
            self.assertIsNone(rows[0].documented)
        finally:
            path.unlink(missing_ok=True)

    def test_skips_non_table_lines(self):
        content = (
            "# Some header\n"
            "Some prose paragraph.\n"
            "| `scan_role_strings.py` | 272 | wf | rule |\n"
            "Another paragraph.\n"
        )
        path = self._write_temp_claude(content)
        try:
            rows = self.mod.parse_claude_md(path)
            self.assertEqual(len(rows), 1)
        finally:
            path.unlink(missing_ok=True)

    def test_missing_file_returns_empty(self):
        rows = self.mod.parse_claude_md(Path("/no/such/file.md"))
        self.assertEqual(rows, [])


class JsonBaselineReaderTests(unittest.TestCase):
    def setUp(self):
        self.mod = _load_module()

    def _patch_map_and_dir(self, mapping: dict, tmpdir: Path):
        return mock.patch.multiple(
            self.mod,
            SCANNER_BASELINE_MAP=mapping,
            BASELINE_DIR=tmpdir,
        )

    def test_reads_finding_count(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            (tmp_path / "fake.json").write_text(
                json.dumps({"finding_count": 42, "findings": []})
            )
            with self._patch_map_and_dir({"fake.py": "fake.json"}, tmp_path):
                self.assertEqual(self.mod._read_json_baseline("fake.py"), 42)

    def test_falls_back_to_total(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            (tmp_path / "f.json").write_text(json.dumps({"total": 17}))
            with self._patch_map_and_dir({"x.py": "f.json"}, tmp_path):
                self.assertEqual(self.mod._read_json_baseline("x.py"), 17)

    def test_falls_back_to_findings_length(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            (tmp_path / "f.json").write_text(
                json.dumps({"findings": [1, 2, 3, 4, 5]})
            )
            with self._patch_map_and_dir({"x.py": "f.json"}, tmp_path):
                self.assertEqual(self.mod._read_json_baseline("x.py"), 5)

    def test_returns_none_when_filter_script(self):
        with self._patch_map_and_dir({"filter.py": None}, Path("/tmp")):
            self.assertIsNone(self.mod._read_json_baseline("filter.py"))

    def test_returns_none_when_file_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self._patch_map_and_dir({"x.py": "absent.json"}, Path(tmp)):
                self.assertIsNone(self.mod._read_json_baseline("x.py"))

    def test_returns_none_on_invalid_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            (tmp_path / "f.json").write_text("not json {")
            with self._patch_map_and_dir({"x.py": "f.json"}, tmp_path):
                self.assertIsNone(self.mod._read_json_baseline("x.py"))


class DriftDetectorTests(unittest.TestCase):
    def setUp(self):
        self.mod = _load_module()

    def _row(self, scanner: str, documented, json_baseline):
        return self.mod.BaselineRow(
            scanner=scanner,
            documented=documented,
            json_baseline=json_baseline,
            raw_baseline_text="(test)",
        )

    def test_matching_doc_and_json_no_drift(self):
        with mock.patch.dict(
            self.mod.SCANNER_BASELINE_MAP, {"x.py": "x.json"}, clear=False
        ):
            drift = self.mod.find_drift([self._row("x.py", 5, 5)])
            self.assertEqual(drift, [])

    def test_doc_disagrees_with_json_is_drift(self):
        with mock.patch.dict(
            self.mod.SCANNER_BASELINE_MAP, {"x.py": "x.json"}, clear=False
        ):
            drift = self.mod.find_drift([self._row("x.py", 5, 7)])
            self.assertEqual(len(drift), 1)
            self.assertIn("doc says 5", drift[0][1])

    def test_missing_json_baseline_is_drift(self):
        with mock.patch.dict(
            self.mod.SCANNER_BASELINE_MAP, {"x.py": "x.json"}, clear=False
        ):
            drift = self.mod.find_drift([self._row("x.py", 5, None)])
            self.assertEqual(len(drift), 1)
            self.assertIn("missing", drift[0][1].lower())

    def test_filter_scanner_with_doc_zero_is_ok(self):
        """Zero-tolerance gates legitimately document '0' without a JSON file."""
        with mock.patch.dict(
            self.mod.SCANNER_BASELINE_MAP, {"filter.py": None}, clear=False
        ):
            drift = self.mod.find_drift([self._row("filter.py", 0, None)])
            self.assertEqual(drift, [])

    def test_filter_scanner_with_nonzero_doc_is_drift(self):
        """A filter script with a non-zero documented count is misleading."""
        with mock.patch.dict(
            self.mod.SCANNER_BASELINE_MAP, {"filter.py": None}, clear=False
        ):
            drift = self.mod.find_drift([self._row("filter.py", 5, None)])
            self.assertEqual(len(drift), 1)

    def test_filter_scanner_with_none_doc_is_ok(self):
        """'n/a' parses to None — that's correct for filter scripts."""
        with mock.patch.dict(
            self.mod.SCANNER_BASELINE_MAP, {"filter.py": None}, clear=False
        ):
            drift = self.mod.find_drift([self._row("filter.py", None, None)])
            self.assertEqual(drift, [])

    def test_doc_non_numeric_when_json_has_count(self):
        with mock.patch.dict(
            self.mod.SCANNER_BASELINE_MAP, {"x.py": "x.json"}, clear=False
        ):
            drift = self.mod.find_drift([self._row("x.py", None, 5)])
            self.assertEqual(len(drift), 1)
            self.assertIn("non-numeric", drift[0][1])



class UnregisteredGatesAreStillCheckedTests(unittest.TestCase):
    """A gate missing from SCANNER_BASELINE_MAP used to be invisible.

    `SCANNER_BASELINE_MAP.get(scanner)` returns None both for a filter script
    that legitimately keeps no baseline AND for a real gate nobody registered.
    Those look identical, so an unregistered gate documenting "0" was read as
    zero-tolerance and skipped. That is how verify_cross_host_template_reverse
    stayed documented as 0 while its baseline held 22 frozen findings, with 68
    of the 96 baseline files on disk unmapped the same way.
    """

    def setUp(self):
        self.mod = _load_module()
        self.tmp = Path(__file__).parent / "_tmp_baselines"
        self.tmp.mkdir(exist_ok=True)
        self._original_dir = self.mod.BASELINE_DIR
        self.mod.BASELINE_DIR = self.tmp

    def tearDown(self):
        self.mod.BASELINE_DIR = self._original_dir
        import shutil

        shutil.rmtree(self.tmp, ignore_errors=True)

    def _row(self, scanner, documented):
        return self.mod.BaselineRow(
            scanner=scanner,
            documented=documented,
            json_baseline=None,
            raw_baseline_text="(test)",
        )

    def _write(self, name, count):
        (self.tmp / name).write_text(
            json.dumps({"finding_count": count}), encoding="utf-8"
        )

    def test_an_unregistered_gate_whose_doc_is_wrong_is_drift(self):
        self._write("security-audit-baseline-ghost-gate.json", 22)
        with mock.patch.dict(self.mod.SCANNER_BASELINE_MAP, {}, clear=False):
            drift = self.mod.find_drift([self._row("verify_ghost_gate.py", 0)])
        self.assertEqual(len(drift), 1, "a lying doc row was skipped again")
        self.assertIn("22", drift[0][1])

    def test_an_unregistered_gate_whose_doc_agrees_is_not_a_finding(self):
        """Housekeeping, not a defect — and reporting it would bury the real one."""
        self._write("security-audit-baseline-ghost-gate.json", 0)
        with mock.patch.dict(self.mod.SCANNER_BASELINE_MAP, {}, clear=False):
            drift = self.mod.find_drift([self._row("verify_ghost_gate.py", 0)])
        self.assertEqual(drift, [])

    def test_a_genuine_filter_script_is_still_excused(self):
        """No baseline file on disk: the original behaviour must survive."""
        with mock.patch.dict(self.mod.SCANNER_BASELINE_MAP, {}, clear=False):
            drift = self.mod.find_drift([self._row("check_nothing.py", 0)])
        self.assertEqual(drift, [])

    def test_the_filename_convention_derives_correctly(self):
        for scanner, expected in (
            ("scan_foo_bar.py", "security-audit-baseline-foo-bar.json"),
            ("verify_foo_bar.py", "security-audit-baseline-foo-bar.json"),
            ("audit_foo.py", "security-audit-baseline-foo.json"),
        ):
            with self.subTest(scanner=scanner):
                self._write(expected, 0)
                self.assertIsNotNone(
                    self.mod._unmapped_baseline_file(scanner), scanner
                )


if __name__ == "__main__":
    unittest.main()
