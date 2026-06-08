#!/usr/bin/env python3
"""Generate self-hosted night-earth equirectangular texture for the WebGL globe.

Reads static/geo/world-countries-110m.json and writes static/img/globe/earth-night-1k.jpg.
Stdlib + Pillow only; safe to re-run (deterministic output dimensions).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GEO_PATH = ROOT / "static/geo/world-countries-110m.json"
OUT_PATH = ROOT / "static/img/globe/earth-night-1k.jpg"

WIDTH = 1024
HEIGHT = 512
OCEAN = (12, 18, 40)
LAND_BASE = (26, 22, 64)
LAND_GLOW = (48, 42, 96)
COAST = (72, 68, 120)


def _ring_to_pixels(ring: list, w: int, h: int) -> list[tuple[int, int]]:
    out: list[tuple[int, int]] = []
    for lng, lat in ring:
        x = int((float(lng) + 180.0) / 360.0 * w)
        y = int((90.0 - float(lat)) / 180.0 * h)
        out.append((max(0, min(w - 1, x)), max(0, min(h - 1, y))))
    return out


def _draw_geometry(draw, geometry: dict, w: int, h: int) -> None:
    gtype = geometry.get("type")
    coords = geometry.get("coordinates")
    if not coords:
        return
    if gtype == "Polygon":
        rings = coords
    elif gtype == "MultiPolygon":
        rings = [ring for poly in coords for ring in poly]
    else:
        return
    for idx, ring in enumerate(rings):
        if len(ring) < 3:
            continue
        pixels = _ring_to_pixels(ring, w, h)
        fill = LAND_GLOW if idx == 0 else OCEAN
        draw.polygon(pixels, fill=fill, outline=COAST if idx == 0 else None)


def generate(out_path: Path = OUT_PATH, width: int = WIDTH, height: int = HEIGHT) -> Path:
    try:
        from PIL import Image, ImageDraw, ImageFilter
    except ImportError as exc:
        raise SystemExit("Pillow required: pip install Pillow") from exc

    if not GEO_PATH.is_file():
        raise SystemExit(f"missing geo asset: {GEO_PATH}")

    geo = json.loads(GEO_PATH.read_text(encoding="utf-8"))
    img = Image.new("RGB", (width, height), OCEAN)
    draw = ImageDraw.Draw(img)
    for feat in geo.get("features") or []:
        geom = feat.get("geometry")
        if isinstance(geom, dict):
            _draw_geometry(draw, geom, width, height)

    img = img.filter(ImageFilter.GaussianBlur(radius=0.6))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path, format="JPEG", quality=88, optimize=True)
    return out_path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true", help="Write texture (default when invoked directly)")
    parser.add_argument("--check", action="store_true", help="Exit 1 if texture missing or stale vs geo")
    args = parser.parse_args()

    if args.check:
        if not OUT_PATH.is_file():
            print(f"FAIL: missing {OUT_PATH}", file=sys.stderr)
            return 1
        if OUT_PATH.stat().st_mtime < GEO_PATH.stat().st_mtime:
            print(f"FAIL: texture older than geo — run {Path(__file__).name}", file=sys.stderr)
            return 1
        print("OK: globe earth texture present")
        return 0

    path = generate()
    print(f"OK: wrote {path} ({path.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
