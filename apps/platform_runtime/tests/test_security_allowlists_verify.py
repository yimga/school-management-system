"""P0: verify_security_allowlists.py contract (review dates + required metadata)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from django.test import SimpleTestCase


class SecurityAllowlistsVerifyTests(SimpleTestCase):
    def test_verify_security_allowlists_passes_on_repo(self):
        root = Path(__file__).resolve().parents[3]
        script = root / "scripts" / "verify_security_allowlists.py"
        self.assertTrue(script.is_file(), f"missing {script}")
        proc = subprocess.run(
            [sys.executable, str(script), "--base", str(root)],
            cwd=str(root),
            capture_output=True,
            text=True,
        )
        self.assertEqual(
            proc.returncode,
            0,
            "verify_security_allowlists.py failed:\n"
            f"{proc.stderr}\n{proc.stdout}",
        )
