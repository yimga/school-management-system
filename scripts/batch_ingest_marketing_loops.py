#!/usr/bin/env python3
"""
Regenerate all manifest buckets from hero + ingest into static/ (operator refresh).

Wraps compress_marketing_loops_from_hero.py then verify gates.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def main() -> int:
    steps = (
        "compress_marketing_loops_from_hero.py",
        "verify_marketing_loop_assets.py",
        "verify_marketing_loop_buckets_distinct.py",
        "verify_marketing_loops_hero_derived.py",
    )
    for script in steps:
        proc = subprocess.run([sys.executable, str(REPO / "scripts" / script)], cwd=REPO)
        if proc.returncode != 0:
            return proc.returncode
    print("batch_ingest_marketing_loops: OK (all buckets ingested)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
