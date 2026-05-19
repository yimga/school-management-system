#!/usr/bin/env python3
"""Gate: scaffold hero-home media files referenced by landing partial exist."""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
REQUIRED = (
    REPO / "static" / "marketing" / "video" / "hero-home.mp4",
    REPO / "static" / "marketing" / "img" / "hero-home-poster.svg",
    REPO / "templates" / "marketing" / "components" / "_hero_home_video.html",
)
MIN_MP4_BYTES = 50_000


def main() -> int:
    errors: list[str] = []
    for path in REQUIRED:
        if not path.is_file():
            errors.append(f"missing: {path.relative_to(REPO)}")
    mp4 = REQUIRED[0]
    if mp4.is_file() and mp4.stat().st_size < MIN_MP4_BYTES:
        errors.append(f"hero-home.mp4 too small ({mp4.stat().st_size} bytes)")
    if errors:
        for e in errors:
            print(f"verify_marketing_hero_media: {e}", file=sys.stderr)
        return 1
    print("verify_marketing_hero_media: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
