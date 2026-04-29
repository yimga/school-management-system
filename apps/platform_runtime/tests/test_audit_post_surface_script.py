"""POST surface audit script produces valid JSON."""

import json
import subprocess
import sys
from pathlib import Path

from django.test import SimpleTestCase


REPO = Path(__file__).resolve().parents[3]
SCRIPT = REPO / "scripts" / "audit_post_surface.py"


class AuditPostSurfaceScriptTests(SimpleTestCase):
    def test_script_exits_zero_and_writes_json(self):
        out_path = REPO / "docs" / "generated" / "post_surface_audit.json"
        proc = subprocess.run(
            [sys.executable, str(SCRIPT)],
            cwd=str(REPO),
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
        )
        self.assertEqual(proc.returncode, 0, msg=proc.stderr or proc.stdout)
        self.assertTrue(out_path.is_file(), msg="expected post_surface_audit.json")
        data = json.loads(out_path.read_text(encoding="utf-8"))
        self.assertEqual(data.get("schema_version"), 2)
        self.assertIn("summary", data)
