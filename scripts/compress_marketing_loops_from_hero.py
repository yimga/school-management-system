#!/usr/bin/env python3
"""
Compress hero-home.mp4 into sub-800KB regional loops (per-bucket ffmpeg profiles).

Falls back to generate_marketing_minimal_loops.py when ffmpeg or hero source is missing.
"""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
MANIFEST = REPO / "docs" / "generated" / "marketing_media_manifest.json"
STATIC = REPO / "static"
HERO = STATIC / "marketing" / "video" / "hero-home.mp4"
MAX_BYTES = 838_860

# Import after path bootstrap for script execution
sys.path.insert(0, str(REPO / "scripts"))
from marketing_loop_ffmpeg import (  # noqa: E402
    BUCKET_PROFILES,
    encode_mp4,
    encode_webm,
    find_ffmpeg,
)


def _write_provenance(data: dict) -> None:
    loops = data.get("loops") or {}
    stamp = datetime.now(UTC).strftime("%Y-%m-%d")
    for bucket, paths in loops.items():
        profile = BUCKET_PROFILES.get(bucket, BUCKET_PROFILES["sovereign_default"])
        paths["provenance"] = (
            f"hero-derived-regional:{bucket}:ss={profile.get('ss', '0')}:"
            f"t={profile.get('t', '6')}:{stamp}"
        )
    data["loops_generated_at"] = stamp
    MANIFEST.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    if not MANIFEST.is_file() or not HERO.is_file():
        print("compress_marketing_loops_from_hero: fallback to minimal loops", file=sys.stderr)
        return subprocess.call([sys.executable, str(REPO / "scripts" / "generate_marketing_minimal_loops.py")])

    ffmpeg = find_ffmpeg()
    if not ffmpeg:
        print("compress_marketing_loops_from_hero: ffmpeg not found — minimal loops", file=sys.stderr)
        return subprocess.call([sys.executable, str(REPO / "scripts" / "generate_marketing_minimal_loops.py")])

    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    ok_any = False
    for bucket, paths in (data.get("loops") or {}).items():
        profile = BUCKET_PROFILES.get(bucket, BUCKET_PROFILES["sovereign_default"])
        mp4 = STATIC / paths["mp4"]
        webm = STATIC / paths["webm"]
        mp4_ok = encode_mp4(ffmpeg, HERO, mp4, profile, MAX_BYTES)
        webm_ok = encode_webm(ffmpeg, HERO, webm, profile, MAX_BYTES) if mp4_ok else False
        if mp4_ok and webm_ok:
            ok_any = True
            print(f"  {bucket}: mp4={mp4.stat().st_size}B webm={webm.stat().st_size}B")
        else:
            print(f"  {bucket}: encode failed", file=sys.stderr)

    if not ok_any:
        return subprocess.call([sys.executable, str(REPO / "scripts" / "generate_marketing_minimal_loops.py")])

    _write_provenance(data)
    print("compress_marketing_loops_from_hero: OK (distinct regional loops)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
