#!/usr/bin/env python3
"""Orchestrates verifiers for §11.4 batches 1331-1337 help-center graft."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _run(script: str) -> int:
    proc = subprocess.run(
        [sys.executable, f"scripts/{script}"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )
    tail = ((proc.stdout or "") + (proc.stderr or "")).strip()[-400:]
    print(tail)
    return proc.returncode


def main() -> int:
    steps = [
        "verify_help_center_tiers.py",
        "verify_support_deflection.py",
        "verify_kb_embedding_coverage.py",
    ]
    for step in steps:
        if _run(step) != 0:
            print(f"verify_help_center_graft_bundles: FAIL at {step}", file=sys.stderr)
            return 1
    proc = subprocess.run(
        [
            sys.executable,
            "scripts/run_support_pipeline_tests_direct.py",
        ],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=600,
    )
    if proc.returncode != 0:
        print((proc.stdout or proc.stderr or "")[-800:], file=sys.stderr)
        return 1
    print("verify_help_center_graft_bundles: HELP_CENTER_GRAFT_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
