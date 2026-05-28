#!/usr/bin/env python3
"""Seed sub-800KB loop placeholders (delegates to generate_marketing_minimal_loops)."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def main() -> int:
    proc = subprocess.run(
        [sys.executable, str(REPO / "scripts" / "generate_marketing_minimal_loops.py")],
        cwd=REPO,
    )
    if proc.returncode != 0:
        print("seed_marketing_loop_placeholders: FAIL", file=sys.stderr)
        return proc.returncode
    print("seed_marketing_loop_placeholders: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
