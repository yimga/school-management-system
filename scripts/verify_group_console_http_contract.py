#!/usr/bin/env python3
"""Group Console HTTP contract gate (Phase 4A poly-institution surface)."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "docs" / "generated" / "group_console_http_contract_audit.json"


def main() -> int:
    parser = argparse.ArgumentParser(description="Group Console HTTP contract verifier")
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()

    failures: list[str] = []
    required = (
        "apps/schools/views_group_console.py",
        "apps/schools/group_console.py",
        "templates/schools/group_console.html",
        "apps/schools/tests/test_group_console_http.py",
    )
    for rel in required:
        if not (REPO / rel).is_file():
            failures.append(f"missing {rel}")

    cmd = [
        sys.executable,
        str(REPO / "scripts" / "run_sqlite_memory_tests.py"),
        "apps.schools.tests.test_group_console_http",
        "apps.schools.tests.test_group_console",
        "--keepdb",
    ]
    env = {**dict(os.environ), "PYTHONUNBUFFERED": "1"}
    try:
        proc = subprocess.run(
            cmd, cwd=str(REPO), capture_output=True, text=True, timeout=600, env=env
        )
    except (subprocess.TimeoutExpired, OSError) as exc:
        failures.append(str(exc))
    else:
        if proc.returncode != 0:
            tail = ((proc.stdout or "") + (proc.stderr or "")).strip()[-400:]
            failures.append(f"group console tests failed: {tail}")

    verdict = (
        "GROUP_CONSOLE_HTTP_CONTRACT_PASS"
        if not failures
        else "GROUP_CONSOLE_HTTP_CONTRACT_FAIL"
    )
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "verdict": verdict,
        "finding_count": len(failures),
        "failures": failures,
    }
    if args.write:
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    if failures:
        print(f"verify_group_console_http_contract: {verdict}", file=sys.stderr)
        for line in failures:
            print(f"  - {line}", file=sys.stderr)
        return 1

    print(f"verify_group_console_http_contract: {verdict}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
