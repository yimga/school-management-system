#!/usr/bin/env python3
"""Fast pre-deploy core gates (CEZGP / deploy parity subset of verify_phases_3_11_gates)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _run(cmd: list[str], label: str) -> int:
    print(f"--- {label} ---", flush=True)
    proc = subprocess.run(cmd, cwd=ROOT)
    if proc.returncode != 0:
        print(f"FAILED: {label}", file=sys.stderr)
        return proc.returncode
    print(f"OK: {label}\n", flush=True)
    return 0


def main() -> int:
    py = sys.executable
    base = ["--base", str(ROOT)]
    steps = [
        ([py, "scripts/check_no_committed_env.py", *base], "Secrets hygiene"),
        ([py, "scripts/check_repo_hygiene.py", *base], "Repo hygiene"),
        ([py, "scripts/check_root_clutter.py", *base], "Root clutter"),
        ([py, "manage.py", "check"], "Django system check"),
        ([py, "manage.py", "makemigrations", "--check", "--dry-run"], "Migrations check"),
        ([py, "scripts/lint_no_print_in_apps.py", *base], "No print() in apps"),
        ([py, "-m", "ruff", "check", "apps", "--select", "F401,F841"], "Ruff F401/F841"),
        ([py, "scripts/scan_operator_shell_dead_hrefs.py", "--strict"], "Dead hrefs strict"),
        ([py, "scripts/scan_print_statements.py", "--compare"], "Print statements baseline"),
    ]
    for cmd, label in steps:
        code = _run(cmd, label)
        if code:
            return code
    print("PREDEPLOY_CORE_GATES_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
