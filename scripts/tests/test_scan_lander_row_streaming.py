"""Regression tests for scan_lander_row_streaming.py."""

from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "scan_lander_row_streaming.py"


class ScanLanderRowStreamingTests(unittest.TestCase):
    def test_clean_tree_passes_strict(self):
        proc = subprocess.run(
            [sys.executable, str(SCRIPT), "--strict"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr or proc.stdout)

    def test_unmarked_list_canonical_rows_fails(self):
        path = ROOT / "apps" / "migration_cloud" / "landers" / "report_lander.py"
        original = path.read_text(encoding="utf-8")
        mutated = original.replace(
            "for _row in canonical_rows:",
            "rows = list(canonical_rows)\n        for _row in rows:",
        )
        try:
            path.write_text(mutated, encoding="utf-8")
            proc = subprocess.run(
                [sys.executable, str(SCRIPT), "--strict"],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(proc.returncode, 1)
            self.assertIn("buffered_canonical_rows", proc.stderr)
        finally:
            path.write_text(original, encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
