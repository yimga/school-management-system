"""Regression tests for verify_sse_tenant_ingress.py."""

from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "verify_sse_tenant_ingress.py"


class VerifySSETenantIngressTests(unittest.TestCase):
    def test_clean_tree_passes(self):
        proc = subprocess.run(
            [sys.executable, str(SCRIPT)],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr or proc.stdout)
        self.assertIn("verify_sse_tenant_ingress: OK", proc.stdout)

    def test_missing_tenant_sse_view_fails(self):
        tenant_path = ROOT / "apps" / "migration_cloud" / "views_tenant_upload.py"
        original = tenant_path.read_text(encoding="utf-8")
        # Must not leave the checked substring behind (X-suffix would still match).
        mutated = original.replace("TenantMigrationProgressStreamView", "RemovedProgressStreamView")
        try:
            tenant_path.write_text(mutated, encoding="utf-8")
            proc = subprocess.run(
                [sys.executable, str(SCRIPT)],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(proc.returncode, 1)
            self.assertIn("tenant progress SSE view missing", proc.stderr)
        finally:
            tenant_path.write_text(original, encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
