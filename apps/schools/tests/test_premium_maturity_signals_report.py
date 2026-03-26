"""CI: premium maturity signal report script (no DB)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from django.test import SimpleTestCase

_ROOT = Path(__file__).resolve().parents[3]


class PremiumMaturitySignalsReportTests(SimpleTestCase):
    def test_report_script_emits_json(self) -> None:
        script = _ROOT / "scripts" / "report_premium_maturity_signals.py"
        if not script.is_file():
            self.skipTest("report_premium_maturity_signals.py not found")
        proc = subprocess.run(
            [sys.executable, str(script), "--json"],
            cwd=_ROOT,
            capture_output=True,
            text=True,
            timeout=120,
        )
        self.assertEqual(
            proc.returncode,
            0,
            msg=(proc.stdout or "") + "\n" + (proc.stderr or ""),
        )
        data = json.loads(proc.stdout)
        self.assertIn("raw_sql_non_migration", data)
        self.assertIn("csrf_exempt", data)
        self.assertIn("litellm_api_key_string", data)
        self.assertIn("gilead_corpus", data)
        for key in (
            "cursor_execute_hits",
            "files_with_hits",
        ):
            self.assertIn(key, data["raw_sql_non_migration"])
