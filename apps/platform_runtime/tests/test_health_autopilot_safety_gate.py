"""Run the health-autopilot safety gate in the suite, because nothing else did.

scripts/verify_health_autopilot_safety.py locks the self-healing engine's safety
contract: every curated remediation reversible, the AI confidence floor enforced,
the apply path policy-gated, no destructive operations, and the operator console's
single write endpoint authenticated and POST-only.

It was named by no gate runner, no CI workflow, no test and no sibling script --
one of 103 verify_/scan_ scripts in that state, of which 30 fail today. This one
failed too, on a check that had gone stale rather than on the engine: it demanded
the literal "staff_member_required" after the endpoint moved to the project's own
@require_control_plane_access, which is strictly stronger.

A security gate nobody runs is indistinguishable from no gate, except that it
looks like coverage in a listing. So it runs here.

The is_file() check is an ASSERT and never a skipTest: a gate that excuses itself
when its subject disappears is the failure this suite keeps finding.
"""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "scripts" / "verify_health_autopilot_safety.py"


def test_health_autopilot_safety_gate_passes():
    assert SCRIPT.is_file(), f"Missing {SCRIPT}"
    proc = subprocess.run(
        [sys.executable, str(SCRIPT)],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        errors="replace",
        timeout=120,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
