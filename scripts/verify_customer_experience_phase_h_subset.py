#!/usr/bin/env python3
"""CEZGP plan phase 8 — Phase H reliable subset (no live URL hits)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    py = sys.executable
    steps = [
        (
            [
                py,
                str(ROOT / "manage.py"),
                "test",
                "apps.accounts.tests.test_smoke_urls",
                "apps.accounts.tests.test_phase_h_ux_verification.PhaseHUrlReverseTests",
                "--noinput",
                "-v",
                "1",
            ],
            "Phase H smoke URLs + URL reverse",
        ),
        ([py, str(ROOT / "scripts/phase_h_audit.py")], "Phase H static audit"),
    ]
    for cmd, label in steps:
        proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=600)
        out = (proc.stdout or "") + (proc.stderr or "")
        if proc.returncode != 0:
            print(f"FAIL: {label}\n{out[-1200:]}", file=sys.stderr)
            return 1
        print(f"OK: {label}")

    print("CUSTOMER_EXPERIENCE_PHASE_H_SUBSET_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
