#!/usr/bin/env python3
"""Regional loops must be hero-derived (not minimal placeholder fingerprints)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
MANIFEST = REPO / "docs" / "generated" / "marketing_media_manifest.json"
STATIC = REPO / "static"
MIN_BRANDED_MP4_BYTES = 40_000


def main() -> int:
    if not MANIFEST.is_file():
        print("verify_marketing_loops_hero_derived: FAIL — manifest missing", file=sys.stderr)
        return 1
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    errors: list[str] = []
    for bucket, paths in (data.get("loops") or {}).items():
        prov = str(paths.get("provenance") or "")
        if not prov.startswith("hero-derived-regional:"):
            errors.append(f"{bucket}: provenance missing hero-derived-regional stamp")
        rel = paths.get("mp4", "")
        p = STATIC / rel
        if not p.is_file():
            errors.append(f"{bucket}: missing mp4 {rel}")
            continue
        size = p.stat().st_size
        if size < MIN_BRANDED_MP4_BYTES:
            errors.append(f"{bucket}: mp4 {size}B < {MIN_BRANDED_MP4_BYTES}B (placeholder?)")
    if errors:
        print("verify_marketing_loops_hero_derived: FAIL", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        return 1
    print("verify_marketing_loops_hero_derived: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
