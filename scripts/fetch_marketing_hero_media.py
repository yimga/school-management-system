#!/usr/bin/env python3
"""Fetch scaffold hero-home.mp4 + poster for marketing landing (CC0 sample loop)."""
from __future__ import annotations

import shutil
import sys
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
VIDEO_DIR = REPO / "static" / "marketing" / "video"
IMG_DIR = REPO / "static" / "marketing" / "img"
# MDN CC0 sample — short loop suitable as scaffold until Sora/Veo hero ships.
VIDEO_URL = "https://interactive-examples.mdn.mozilla.net/media/cc0-videos/flower.mp4"
POSTER_SRC = REPO / "static" / "images" / "marketing" / "hero-global-os-composite.svg"


def main() -> int:
    VIDEO_DIR.mkdir(parents=True, exist_ok=True)
    IMG_DIR.mkdir(parents=True, exist_ok=True)
    dest_mp4 = VIDEO_DIR / "hero-home.mp4"
    dest_poster = IMG_DIR / "hero-home-poster.svg"

    print(f"fetch {VIDEO_URL}")
    urllib.request.urlretrieve(VIDEO_URL, dest_mp4)
    if dest_mp4.stat().st_size < 5000:
        print("ERROR: hero-home.mp4 too small", file=sys.stderr)
        return 1

    if POSTER_SRC.is_file():
        shutil.copy2(POSTER_SRC, dest_poster)
        print(f"poster {dest_poster.relative_to(REPO)}")
    else:
        print("WARN: poster SVG missing", file=sys.stderr)

    print(f"OK: {dest_mp4.relative_to(REPO)} ({dest_mp4.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
