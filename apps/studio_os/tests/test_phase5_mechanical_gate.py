"""Re-run mechanical Phase 5 verifier in CI (same bar as a second audit)."""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "scripts" / "verify_cursor_phase5_studio_os.py"


def test_cursor_phase5_mechanical_verify_script_passes():
    assert SCRIPT.is_file(), f"Missing {SCRIPT}"
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--base", str(ROOT)],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert proc.returncode == 0, proc.stderr + proc.stdout
