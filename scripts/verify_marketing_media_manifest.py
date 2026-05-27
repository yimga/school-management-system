#!/usr/bin/env python3
"""Verify marketing_media_manifest.json structure and loop file presence."""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
MANIFEST = REPO / "docs" / "generated" / "marketing_media_manifest.json"
STATIC = REPO / "static"


def main() -> int:
    errors: list[str] = []
    if not MANIFEST.is_file():
        print("verify_marketing_media_manifest: FAIL — manifest missing", file=sys.stderr)
        return 1
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    loops = data.get("loops") or {}
    max_bytes = int(data.get("max_loop_bytes", 838860))
    for bucket, paths in loops.items():
        mp4 = paths.get("mp4", "")
        webm = paths.get("webm", "")
        mp4_path = STATIC / mp4 if mp4 else None
        webm_path = STATIC / webm if webm else None
        if not mp4_path or not mp4_path.is_file():
            errors.append(f"missing mp4 for {bucket}: {mp4}")
        elif mp4_path.stat().st_size > max_bytes:
            errors.append(f"mp4 too large for {bucket}: {mp4_path.stat().st_size} > {max_bytes}")
        if not webm_path or not webm_path.is_file():
            errors.append(f"missing webm for {bucket}: {webm}")
        elif webm_path.stat().st_size > max_bytes:
            errors.append(f"webm too large for {bucket}: {webm_path.stat().st_size} > {max_bytes}")
        poster = paths.get("poster", "")
        if poster and not (STATIC / poster).is_file():
            errors.append(f"missing poster for {bucket}: {poster}")
    sections = data.get("homepage_sections") or []
    required = {"sovereign_kernel", "clinical_ledger", "rugged_engine", "fluid_classroom"}
    if not required.issubset(set(sections)):
        errors.append(f"homepage_sections missing required: {required - set(sections)}")
    if errors:
        print("verify_marketing_media_manifest: FAIL", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        return 1
    print("verify_marketing_media_manifest: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
