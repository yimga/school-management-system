"""CI: static gates for Program Phase 10 (ecosystem) + Phase 11 (marketing narrative)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from django.test import SimpleTestCase

_ROOT = Path(__file__).resolve().parents[3]


class ProgramPhase10Phase11GateTests(SimpleTestCase):
    def test_static_gate_script_passes(self) -> None:
        proc = subprocess.run(
            [sys.executable, str(_ROOT / "scripts/verify_program_phase10_phase11_gates.py")],
            cwd=_ROOT,
            capture_output=True,
            text=True,
            timeout=60,
        )
        self.assertEqual(
            proc.returncode,
            0,
            msg=(proc.stdout or "") + "\n" + (proc.stderr or ""),
        )
