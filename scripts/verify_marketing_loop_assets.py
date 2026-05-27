#!/usr/bin/env python3
"""Ensure marketing loop buckets have mp4+webm under size budget."""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
MANIFEST = REPO / "docs" / "generated" / "marketing_media_manifest.json"
STATIC = REPO / "static"


def main() -> int:
    if not MANIFEST.is_file():
        print("verify_marketing_loop_assets: FAIL — manifest missing", file=sys.stderr)
        return 1
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    max_bytes = int(data.get("max_loop_bytes", 838860))
    errors: list[str] = []
    for bucket, paths in (data.get("loops") or {}).items():
        for kind in ("mp4", "webm"):
            rel = paths.get(kind, "")
            p = STATIC / rel
            if not p.is_file():
                errors.append(f"{bucket}.{kind} missing: {rel}")
            elif p.stat().st_size > max_bytes:
                errors.append(f"{bucket}.{kind} exceeds {max_bytes}B: {p.stat().st_size}")
    if errors:
        print("verify_marketing_loop_assets: FAIL", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        return 1
    print("verify_marketing_loop_assets: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
