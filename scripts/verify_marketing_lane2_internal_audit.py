#!/usr/bin/env python3
"""One-shot internal audit for marketing + Lane 2 repo-contained work (batches 1546–1549)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

GATES = (
    "scripts/verify_marketing_personality_pages.py",
    "scripts/verify_marketing_intent_viewport.py",
    "scripts/verify_marketing_intent_homepage_optin.py",
    "scripts/verify_marketing_simulated_benchmark_disclosure.py",
    "scripts/verify_lane2_external_honesty.py",
    "scripts/verify_lane2_residuals_on_disk.py",
    "scripts/verify_pilot_defect_intake.py",
    "scripts/verify_lane2_partial_queue_closeout.py",
    "scripts/verify_marketing_glocal_visual_engine.py",
    "scripts/verify_marketing_css_bundles_fresh.py",
    "scripts/verify_service_worker_version.py",
)


def main() -> int:
    errors: list[str] = []
    for rel in GATES:
        extra: list[str] = []
        if rel.endswith("verify_service_worker_version.py"):
            extra = ["--check-monotonic"]
        proc = subprocess.run(
            [sys.executable, str(REPO / rel), *extra],
            cwd=REPO,
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            errors.append(f"{rel}:\n{proc.stderr or proc.stdout}")
        else:
            line = (proc.stdout or "").strip().splitlines()[-1:] or [rel]
            print(line[0])

    if errors:
        print("verify_marketing_lane2_internal_audit: FAIL", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        return 1

    print("verify_marketing_lane2_internal_audit: MARKETING_LANE2_INTERNAL_AUDIT_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
