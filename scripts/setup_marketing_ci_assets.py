#!/usr/bin/env python3
"""Ensure marketing hero video + self-hosted fonts exist (CI + fresh clones)."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
HERO_MP4 = REPO / "static" / "marketing" / "video" / "hero-home.mp4"
ENSURE_LOOPS = REPO / "scripts" / "ensure_marketing_loops.py"
FONT_400 = (
    REPO
    / "static"
    / "marketing"
    / "fonts"
    / "source-serif-4"
    / "source-serif-4-latin-400-normal.woff2"
)
FETCH_HERO = REPO / "scripts" / "fetch_marketing_hero_media.py"
FETCH_FONTS = REPO / "scripts" / "fetch_marketing_fonts.py"


def _run(script: Path) -> None:
    proc = subprocess.run([sys.executable, str(script)], cwd=REPO)
    if proc.returncode != 0:
        raise SystemExit(proc.returncode)


def main() -> int:
    if not HERO_MP4.is_file() or HERO_MP4.stat().st_size < 50_000:
        print("setup_marketing_ci_assets: fetching hero media…")
        _run(FETCH_HERO)
    if not FONT_400.is_file():
        print("setup_marketing_ci_assets: fetching Source Serif 4…")
        _run(FETCH_FONTS)
    print("setup_marketing_ci_assets: ensuring regional loops…")
    _run(ENSURE_LOOPS)
    print("setup_marketing_ci_assets: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
