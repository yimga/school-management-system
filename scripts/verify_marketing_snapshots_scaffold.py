#!/usr/bin/env python3
"""Repo gate: marketing visual-regression scaffold is wired (batch 1264)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

REQUIRED = (
    "tests/e2e/marketing-snapshots.spec.js",
    "scripts/run_marketing_snapshots.sh",
    ".github/workflows/marketing-snapshots.yml",
)


def main() -> int:
    missing = [rel for rel in REQUIRED if not (ROOT / rel).is_file()]
    if missing:
        for rel in missing:
            print(f"verify_marketing_snapshots_scaffold: missing {rel}", file=sys.stderr)
        return 1
    print("verify_marketing_snapshots_scaffold: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
