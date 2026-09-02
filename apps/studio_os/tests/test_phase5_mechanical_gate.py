"""Re-run mechanical Phase 5 verifier in CI (same bar as a second audit).

This named scripts/verify_cursor_phase5_studio_os.py, which was deleted in
aff798771 ("Complete security backlog implementation and repo cleanup") and
never replaced here -- so this test has been RED ever since, and the gate it
stands for has not run. Its successor is
scripts/verify_phase5_studio_os_conformance.py: same subject (Studio OS
Phase 5), same --base interface, and a wider bar (mode contracts, legacy
redirect coverage, output native constraints). It is the script named in
docs/PHASES_3_11_GATE_VERIFICATION.md, scripts/pre_deploy_gate.sh and
docs/phase_checklists/README.md.

The is_file() assert stays an ASSERT and never becomes a skipTest: a gate
that excuses itself when its subject disappears is the exact failure that
let this one sit red -- except it would have reported "skipped" instead.
"""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "scripts" / "verify_phase5_studio_os_conformance.py"


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
