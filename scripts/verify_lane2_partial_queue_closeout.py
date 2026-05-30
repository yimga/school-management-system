#!/usr/bin/env python3
"""
Lane 2 partial forward-queue repo closeout orchestrator (batch 1573).

Runs on-disk evidence + honesty gates for batches 1170 / 1199 / 1175 intake
and CEZGP matrix partial-row repo proofs. Does not fabricate live PSP or
hosted deploy SHA evidence.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _run(label: str, rel: str) -> int:
    cmd = [sys.executable, str(ROOT / rel)]
    print(f"--- {label} ---", flush=True)
    proc = subprocess.run(cmd, cwd=ROOT)
    if proc.returncode != 0:
        print(f"verify_lane2_partial_queue_closeout: FAIL at {label}", file=sys.stderr)
        return proc.returncode
    print(f"OK: {label}\n", flush=True)
    return 0


def main() -> int:
    steps = [
        ("verify_lane2_residuals_on_disk", "scripts/verify_lane2_residuals_on_disk.py"),
        ("verify_lane2_external_honesty", "scripts/verify_lane2_external_honesty.py"),
        ("verify_pilot_defect_intake", "scripts/verify_pilot_defect_intake.py"),
        (
            "verify_customer_experience_lane2_partial_closeout",
            "scripts/verify_customer_experience_lane2_partial_closeout.py",
        ),
    ]
    for label, rel in steps:
        code = _run(label, rel)
        if code:
            return code

    rollup = ROOT / "docs" / "generated" / "geos_lane2_residual_evidence.json"
    if not rollup.is_file():
        print("verify_lane2_partial_queue_closeout: missing geos_lane2_residual_evidence.json", file=sys.stderr)
        return 1

    print("verify_lane2_partial_queue_closeout: LANE2_PARTIAL_QUEUE_CLOSEOUT_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
