#!/usr/bin/env python3
"""Run unbounded collection audit; exit 1 on findings unless baseline allows."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / "var" / "security-audit-baseline-unbounded-collection.json"
AUDIT = ROOT / "scripts" / "audit_unbounded_collection_surfaces.py"


def main() -> int:
    proc = subprocess.run(
        [sys.executable, str(AUDIT), "--json"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    if proc.returncode not in (0, 1):
        print(proc.stdout or proc.stderr, file=sys.stderr)
        return proc.returncode or 1
    payload = json.loads(proc.stdout)
    count = int(payload.get("finding_count", 0))
    baseline_count = 0
    if BASELINE.is_file():
        baseline_count = int(
            json.loads(BASELINE.read_text(encoding="utf-8")).get("finding_count", 0)
        )
    print(f"verify_unbounded_collection_surfaces: findings={count} baseline={baseline_count}")
    if count > baseline_count:
        for finding in payload.get("findings", [])[:20]:
            print(
                f"  {finding['kind']} {finding['file']}:{finding['line']} — {finding['detail']}"
            )
        return 1
    if count == 0:
        print("UNBOUNDED_COLLECTION_SURFACE_PASS")
        return 0
    print("UNBOUNDED_COLLECTION_SURFACE_BASELINE_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
