"""Wedge line registry: 45 rows invariants (no DB)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from django.test import SimpleTestCase

from apps.platform_runtime.wedge_line_registry import (
    BEACHHEAD_BLUEPRINT_PACKS,
    WEDGE_LINES,
    assert_wedge_lines_complete,
    wedge_phase,
)

REPO = Path(__file__).resolve().parents[3]


class WedgeLineRegistryTests(SimpleTestCase):
    def test_forty_five_rows_ordered_phases(self):
        assert_wedge_lines_complete()
        self.assertEqual(len(WEDGE_LINES), 45)
        for row in WEDGE_LINES:
            wid = int(row["id"])
            self.assertEqual(int(row["phase"]), wedge_phase(wid))
        self.assertEqual(BEACHHEAD_BLUEPRINT_PACKS[0]["slug"], "ib-world-school")

    def test_verify_script_passes(self):
        script = REPO / "scripts" / "verify_wedge_line_registry.py"
        r = subprocess.run(
            [sys.executable, str(script)],
            cwd=str(REPO),
            capture_output=True,
            text=True,
            timeout=120,
        )
        self.assertEqual(
            r.returncode,
            0,
            r.stdout + r.stderr,
        )
