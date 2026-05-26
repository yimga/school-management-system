#!/usr/bin/env python3
"""Master gate for local-first / sovereign offline completion (batch 1510)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

GATES = (
    ("verify_local_first_surface_wiring.py", []),
    ("verify_offline_workflow_apply.py", []),
    ("verify_sovereign_offline_depth.py", []),
    ("verify_sovereign_offline_foundation.py", []),
    ("verify_cdn_self_host_burndown.py", []),
)


def main() -> int:
    failures: list[str] = []
    for script, extra in GATES:
        cmd = [sys.executable, str(ROOT / "scripts" / script), *extra]
        proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
        if proc.returncode != 0:
            failures.append(script)
            if proc.stdout:
                print(proc.stdout, file=sys.stderr)
            if proc.stderr:
                print(proc.stderr, file=sys.stderr)
    if failures:
        print("verify_local_first_completion: FAIL", file=sys.stderr)
        for name in failures:
            print(f"  - {name}", file=sys.stderr)
        return 1
    print("verify_local_first_completion: LOCAL_FIRST_COMPLETION_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
