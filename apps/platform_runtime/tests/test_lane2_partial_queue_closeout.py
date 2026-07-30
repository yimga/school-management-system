"""Lane 2 partial queue closeout verifier smoke."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from django.test import SimpleTestCase

ROOT = Path(__file__).resolve().parents[3]


class Lane2PartialQueueCloseoutTests(SimpleTestCase):
    def test_lane2_partial_queue_closeout_passes(self):
        proc = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "verify_lane2_partial_queue_closeout.py")],
            cwd=ROOT,
            capture_output=True,
            text=True,
            # Windows text=True defaults to cp1252 and crashes decoding the
            # verifier's UTF-8 output (em-dashes / smart quotes); force UTF-8.
            encoding="utf-8",
            errors="replace",
        )
        self.assertEqual(
            proc.returncode,
            0,
            msg=(proc.stdout or "") + (proc.stderr or ""),
        )
        self.assertIn("LANE2_PARTIAL_QUEUE_CLOSEOUT_PASS", proc.stdout)
