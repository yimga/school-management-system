"""North Star audit + kill test writers (structural)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from django.test import SimpleTestCase

REPO = Path(__file__).resolve().parents[3]


class NorthstarAuditKillTestScriptTests(SimpleTestCase):
    def test_audit_outputs_sections_when_run(self):
        subprocess.run(
            [sys.executable, str(REPO / "scripts" / "run_northstar_audit.py")],
            cwd=str(REPO),
            capture_output=True,
            text=True,
            timeout=2400,
        )
        js = REPO / "docs" / "generated" / "northstar_audit.json"
        if js.is_file():
            data = json.loads(js.read_text(encoding="utf-8"))
            self.assertIn("sections", data)
            self.assertIn("total_score", data)

    def test_kill_test_writes_reports(self):
        proc = subprocess.run(
            [sys.executable, str(REPO / "scripts" / "run_kill_test.py")],
            cwd=str(REPO),
            capture_output=True,
            text=True,
            timeout=7200,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr or proc.stdout)
        js = REPO / "docs" / "generated" / "kill_test_report.json"
        self.assertTrue(js.is_file())
        data = json.loads(js.read_text(encoding="utf-8"))
        self.assertIn("scenarios", data)
        self.assertIn("result", data)
        ids = {s.get("id") for s in (data.get("scenarios") or [])}
        self.assertIn("degraded_surface_fallbacks", ids)
