"""
Gate: phased wedge execution (1–45 in five bands) — scripts/validate_wedges_phase.py.

Ensures super-premium phases + catalog invariants stay wired after refactors.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from django.test import SimpleTestCase


REPO = Path(__file__).resolve().parents[3]


class ValidateWedgesPhaseScriptTests(SimpleTestCase):
    allow_database_queries = True  # script may import Django ORM modules

    def test_validate_wedges_phase_all_passes(self):
        script = REPO / "scripts" / "validate_wedges_phase.py"
        self.assertTrue(script.is_file(), f"Missing {script}")
        r = subprocess.run(
            [sys.executable, str(script), "--base", str(REPO), "--phase", "all"],
            cwd=str(REPO),
            capture_output=True,
            text=True,
            timeout=180,
        )
        if r.returncode != 0:
            self.fail(
                "validate_wedges_phase.py --phase all failed:\n"
                + (r.stdout or "")
                + (r.stderr or "")
            )
