#!/usr/bin/env python3
"""Multi-campus Wedge 22 HTTP contract gate (control-plane rollup surfaces)."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "docs" / "generated" / "multicampus_wedge_http_contract_audit.json"


def main() -> int:
    parser = argparse.ArgumentParser(description="Multicampus wedge HTTP contract verifier")
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()

    failures: list[str] = []
    required = (
        "apps/portal/views_multicampus_billing.py",
        "apps/portal/views_multicampus_academics.py",
        "apps/portal/views_multicampus_extension.py",
        "apps/portal/tests/test_multicampus_wedge_http.py",
    )
    for rel in required:
        if not (REPO / rel).is_file():
            failures.append(f"missing {rel}")

    cmd = [
        sys.executable,
        str(REPO / "scripts" / "run_sqlite_memory_tests.py"),
        "apps.portal.tests.test_multicampus_wedge_http",
        "--fresh",
    ]
    try:
        proc = subprocess.run(cmd, cwd=str(REPO), capture_output=True, text=True, timeout=300)
    except (subprocess.TimeoutExpired, OSError) as exc:
        failures.append(str(exc))
    else:
        if proc.returncode != 0:
            tail = ((proc.stdout or "") + (proc.stderr or "")).strip()[-400:]
            failures.append(f"multicampus wedge HTTP tests failed: {tail}")

    verdict = (
        "MULTICAMPUS_WEDGE_HTTP_CONTRACT_PASS"
        if not failures
        else "MULTICAMPUS_WEDGE_HTTP_CONTRACT_FAIL"
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
        print(f"verify_multicampus_wedge_http_contract: {verdict}", file=sys.stderr)
        for line in failures:
            print(f"  - {line}", file=sys.stderr)
        return 1

    print(f"verify_multicampus_wedge_http_contract: {verdict}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
