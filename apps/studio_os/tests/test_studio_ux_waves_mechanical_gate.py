"""Wave 6 — subprocess gate for Studio OS UX waves 1–5 (no DB)."""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "scripts" / "verify_studio_os_ux_waves.py"


def test_studio_os_ux_waves_mechanical_gate_passes():
    assert SCRIPT.is_file(), f"Missing {SCRIPT}"
    proc = subprocess.run(
        [sys.executable, str(SCRIPT)],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert proc.returncode == 0, proc.stderr + proc.stdout
