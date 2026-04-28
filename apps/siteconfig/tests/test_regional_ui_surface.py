"""Regional UI audit script produces generated artifacts."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from django.test import SimpleTestCase

REPO = Path(__file__).resolve().parents[3]


class RegionalUiSurfaceAuditTests(SimpleTestCase):
    def test_audit_script_writes_json_and_md(self):
        r = subprocess.run(
            [sys.executable, str(REPO / "scripts" / "audit_regional_ui_surface.py")],
            cwd=str(REPO),
            capture_output=True,
            text=True,
            timeout=120,
        )
        self.assertEqual(r.returncode, 0, msg=(r.stderr or r.stdout)[:2000])
        js = REPO / "docs" / "generated" / "regional_ui_surface_audit.json"
        md = REPO / "docs" / "generated" / "regional_ui_surface_audit.md"
        self.assertTrue(js.is_file(), msg="expected JSON output")
        self.assertTrue(md.is_file(), msg="expected Markdown output")
