"""Regression tests for verify_migration_apply_stall_contract.py."""

from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "verify_migration_apply_stall_contract.py"


class VerifyMigrationApplyStallContractTests(unittest.TestCase):
    def test_clean_tree_passes(self):
        proc = subprocess.run(
            [sys.executable, str(SCRIPT)],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr or proc.stdout)
        self.assertIn("verify_migration_apply_stall_contract: OK", proc.stdout)

    def test_missing_row_progress_token_fails(self):
        path = ROOT / "apps" / "migration_cloud" / "loop_watchdog.py"
        original = path.read_text(encoding="utf-8")
        mutated = original.replace("rows_processed", "row_progress_n")
        try:
            path.write_text(mutated, encoding="utf-8")
            proc = subprocess.run(
                [sys.executable, str(SCRIPT)],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(proc.returncode, 1)
            self.assertIn("rows_processed", proc.stderr)
        finally:
            path.write_text(original, encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
