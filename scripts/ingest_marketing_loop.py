#!/usr/bin/env python3
"""
Ingest a produced marketing loop into the manifest bucket (mp4 + optional webm).

Usage:
  python scripts/ingest_marketing_loop.py --bucket sovereign_us --mp4 path/to/loop.mp4 [--webm path/to/loop.webm]
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
MANIFEST = REPO / "docs" / "generated" / "marketing_media_manifest.json"
STATIC = REPO / "static"
MAX_BYTES = 838_860


def main() -> int:
    parser = argparse.ArgumentParser(description="Ingest marketing loop asset")
    parser.add_argument("--bucket", required=True)
    parser.add_argument("--mp4", required=True, type=Path)
    parser.add_argument("--webm", type=Path, default=None)
    args = parser.parse_args()
    if not MANIFEST.is_file():
        print("manifest missing", file=sys.stderr)
        return 1
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    loops = data.get("loops") or {}
    if args.bucket not in loops:
        print(f"unknown bucket: {args.bucket}", file=sys.stderr)
        return 1
    mp4_src = args.mp4.resolve()
    if not mp4_src.is_file():
        print(f"mp4 not found: {mp4_src}", file=sys.stderr)
        return 1
    if mp4_src.stat().st_size > MAX_BYTES:
        print(f"mp4 {mp4_src.stat().st_size}B exceeds {MAX_BYTES}B budget", file=sys.stderr)
        return 1
    dest_mp4 = STATIC / loops[args.bucket]["mp4"]
    dest_mp4.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(mp4_src, dest_mp4)
    webm_src = args.webm
    if webm_src and webm_src.is_file():
        if webm_src.stat().st_size > MAX_BYTES:
            print(f"webm exceeds budget", file=sys.stderr)
            return 1
        dest_webm = STATIC / loops[args.bucket]["webm"]
        shutil.copy2(webm_src, dest_webm)
    print(f"ingest_marketing_loop: OK bucket={args.bucket}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
