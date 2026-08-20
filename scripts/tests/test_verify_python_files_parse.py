"""Tests for the floor gate: every Python file in the tree must compile.

The live-tree test at the bottom doubles as calibration — if the gate ever starts
reporting findings on a clean checkout it is the gate that is wrong, not the tree.
"""
from __future__ import annotations

import io
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import verify_python_files_parse as gate  # noqa: E402


class _TempTree(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self._real_root = gate.REPO_ROOT
        gate.REPO_ROOT = self.root
        (self.root / "apps").mkdir()

    def tearDown(self):
        gate.REPO_ROOT = self._real_root
        self._tmp.cleanup()

    def _write(self, rel, text):
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        with io.open(path, "w", encoding="utf8", newline="\n") as fh:
            fh.write(text)
        return path


class PythonParseGateTests(_TempTree):
    def test_a_clean_file_is_not_a_finding(self):
        self._write("apps/ok.py", "def f():\n    return 1\n")
        checked, findings = gate.scan(("apps",))
        self.assertEqual(checked, 1)
        self.assertEqual(findings, [])

    def test_the_real_breakage_is_caught(self):
        """The exact shape found on main: a file truncated mid-statement."""
        self._write("apps/tasks.py", 'def f():\n    return {\n        "ok": True,\n')
        _checked, findings = gate.scan(("apps",))
        self.assertEqual(len(findings), 1)
        rel, lineno, msg = findings[0]
        self.assertEqual(rel, "apps/tasks.py")
        self.assertEqual(lineno, 2)
        self.assertIn("never closed", msg)

    def test_an_ordinary_syntax_error_is_caught(self):
        self._write("apps/bad.py", "def f(:\n    pass\n")
        _checked, findings = gate.scan(("apps",))
        self.assertEqual(len(findings), 1)

    def test_pycache_is_skipped(self):
        self._write("apps/__pycache__/x.py", "this is ( not python")
        checked, findings = gate.scan(("apps",))
        self.assertEqual(checked, 0)
        self.assertEqual(findings, [])

    def test_a_missing_root_is_not_an_error(self):
        checked, findings = gate.scan(("does_not_exist",))
        self.assertEqual((checked, findings), (0, []))

    def test_main_exits_nonzero_on_a_finding(self):
        self._write("apps/bad.py", "def f(:\n")
        self.assertEqual(gate.main(["--roots", "apps"]), 1)

    def test_main_exits_zero_when_clean(self):
        self._write("apps/ok.py", "x = 1\n")
        self.assertEqual(gate.main(["--roots", "apps"]), 0)


class LiveTreeTests(unittest.TestCase):
    def test_the_repository_parses(self):
        """Calibration: a clean checkout must be clean."""
        checked, findings = gate.scan()
        self.assertGreater(checked, 1000, "the gate is not finding the source tree")
        self.assertEqual(
            findings,
            [],
            "files that do not compile:\n  "
            + "\n  ".join(f"{r}:{n}: {m}" for r, n, m in findings),
        )


if __name__ == "__main__":
    unittest.main()
