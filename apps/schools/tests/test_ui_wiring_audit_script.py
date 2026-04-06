"""CI: template URL literal + href wiring audit (Django urlconf walk, no DB)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from django.test import SimpleTestCase

_ROOT = Path(__file__).resolve().parents[3]


class UiWiringAuditScriptTests(SimpleTestCase):
    def test_verify_ui_wiring_audit_passes(self) -> None:
        proc = subprocess.run(
            [
                sys.executable,
                str(_ROOT / "scripts/verify_ui_wiring_audit.py"),
                "--base",
                str(_ROOT),
            ],
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
