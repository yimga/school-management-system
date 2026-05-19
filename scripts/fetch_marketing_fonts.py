#!/usr/bin/env python3
"""Download self-hosted Source Serif 4 WOFF2 files for the marketing shell."""
from __future__ import annotations

import sys
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
OUT_DIR = REPO / "static" / "marketing" / "fonts" / "source-serif-4"
BASE = "https://cdn.jsdelivr.net/fontsource/fonts/source-serif-4@5.2.5"

FILES = {
    "source-serif-4-latin-400-normal.woff2": f"{BASE}/latin-400-normal.woff2",
    "source-serif-4-latin-600-normal.woff2": f"{BASE}/latin-600-normal.woff2",
    "source-serif-4-latin-700-normal.woff2": f"{BASE}/latin-700-normal.woff2",
}


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for name, url in FILES.items():
        dest = OUT_DIR / name
        print(f"fetch {url} -> {dest.relative_to(REPO)}")
        urllib.request.urlretrieve(url, dest)
        if dest.stat().st_size < 1000:
            print(f"ERROR: {name} suspiciously small", file=sys.stderr)
            return 1
    print("OK: marketing fonts ready")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
