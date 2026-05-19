#!/usr/bin/env python3
"""Marketing public-surface LCP + CLS budget gate (Playwright Performance API).

See scripts/verify_marketing_lighthouse_budget.mjs for env knobs.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PROBE = REPO / "scripts" / "verify_marketing_lighthouse_budget.mjs"


def main() -> int:
    if not PROBE.is_file():
        print(f"missing probe script: {PROBE}", file=sys.stderr)
        return 1

    env = os.environ.copy()
    env.setdefault("MKT_LIGHTHOUSE_STRICT", "1")
    proc = subprocess.run(["node", str(PROBE)], cwd=REPO, env=env)
    return proc.returncode


if __name__ == "__main__":
    raise SystemExit(main())
