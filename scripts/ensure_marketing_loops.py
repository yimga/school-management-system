#!/usr/bin/env python3
"""
Ensure regional marketing loops exist for CI and local gates.

Uses committed static files when present and distinct; otherwise runs
compress_marketing_loops_from_hero.py (ffmpeg) or minimal placeholders.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def _gate(script: str) -> int:
    return subprocess.call([sys.executable, str(REPO / "scripts" / script)], cwd=REPO)


def main() -> int:
    parser = argparse.ArgumentParser(description="Ensure marketing loop assets")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Regenerate loops even when committed assets pass gates",
    )
    args = parser.parse_args()

    if not args.force:
        assets_rc = _gate("verify_marketing_loop_assets.py")
        distinct_rc = _gate("verify_marketing_loop_buckets_distinct.py")
        hero_rc = _gate("verify_marketing_loops_hero_derived.py")
        if assets_rc == 0 and distinct_rc == 0 and hero_rc == 0:
            print("ensure_marketing_loops: OK (committed regional loops)")
            return 0

    rc = subprocess.call(
        [sys.executable, str(REPO / "scripts" / "compress_marketing_loops_from_hero.py")],
        cwd=REPO,
    )
    if rc != 0:
        return rc
    if _gate("verify_marketing_loop_buckets_distinct.py") != 0:
        return 1
    return _gate("verify_marketing_loops_hero_derived.py")


if __name__ == "__main__":
    raise SystemExit(main())
