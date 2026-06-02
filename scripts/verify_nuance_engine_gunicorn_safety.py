#!/usr/bin/env python3
"""
Gunicorn-safe nuance engine gate (Render SIGALRM worker-thread regression).

Runs:
  - scan_sigalrm_worker_thread_safety.py --strict (baseline 0)
  - scan_nuance_safe_eval_imports.py --strict (baseline 0)
  - verify_nuance_logic_toolset_contract.py
  - Django tests for worker-thread verify_nuance_safety / evaluate_json_logic / toolset contract

Exit 0 prints NUANCE_ENGINE_GUNICORN_SAFETY_PASS.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def _run(cmd: list[str]) -> int:
    proc = subprocess.run(cmd, cwd=REPO_ROOT)
    return int(proc.returncode)


def main() -> int:
    py = sys.executable
    if _run([py, "scripts/scan_sigalrm_worker_thread_safety.py", "--strict"]) != 0:
        print("NUANCE_ENGINE_GUNICORN_SAFETY_FAIL: sigalrm scanner", file=sys.stderr)
        return 1
    if _run([py, "scripts/scan_nuance_safe_eval_imports.py", "--strict"]) != 0:
        print("NUANCE_LOGIC_TOOLSET_CONTRACT_FAIL: safe_eval import scanner", file=sys.stderr)
        return 1
    if _run([py, "scripts/verify_nuance_logic_toolset_contract.py"]) != 0:
        print("NUANCE_LOGIC_TOOLSET_CONTRACT_FAIL: contract verifier", file=sys.stderr)
        return 1
    if _run(
        [
            py,
            "scripts/run_sqlite_memory_tests.py",
            "apps.siteconfig.tests.test_nuance_engine_worker_thread_timeout",
            "apps.siteconfig.tests.test_nuance_logic_toolset_contract",
            "apps.policies.tests.test_grading_nuance_templates",
            "--no-input",
        ]
    ) != 0:
        print("NUANCE_ENGINE_GUNICORN_SAFETY_FAIL: django tests", file=sys.stderr)
        return 1
    print("NUANCE_ENGINE_GUNICORN_SAFETY_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
