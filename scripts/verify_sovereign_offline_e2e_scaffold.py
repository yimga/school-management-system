#!/usr/bin/env python3
"""SODP E2E + GEOS evidence scaffold gate."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    findings: list[str] = []
    for rel in (
        "apps/sync_engine/delta_bundle.py",
        "apps/api/sync_bundle_api.py",
        "tests/e2e/offline-queue-replay.spec.js",
    ):
        if not (ROOT / rel).is_file():
            findings.append(f"missing {rel}")
    evidence_dir = ROOT / "var/evidence/geos-99/offline"
    if not evidence_dir.is_dir():
        findings.append(f"missing {evidence_dir.relative_to(ROOT)}")
    if findings:
        print("verify_sovereign_offline_e2e_scaffold: FAIL", file=sys.stderr)
        for item in findings:
            print(f"  - {item}", file=sys.stderr)
        return 1
    print("verify_sovereign_offline_e2e_scaffold: SOVEREIGN_OFFLINE_E2E_SCAFFOLD_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
