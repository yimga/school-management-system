#!/usr/bin/env python3
"""Generate self-hosted earth equirectangular texture for the WebGL globe.

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
OCEAN_DEEP = (9, 25, 54)
OCEAN_SHELF = (25, 78, 126)
COAST = (214, 198, 150)


def _clamp_channel(value: float) -> int:
    return max(0, min(255, int(round(value))))


def _mix(a: tuple[int, int, int], b: tuple[int, int, int], t: float) -> tuple[int, int, int]:
    t = max(0.0, min(1.0, t))
    return tuple(_clamp_channel(a[i] * (1.0 - t) + b[i] * t) for i in range(3))


def _centroid(ring: list) -> tuple[float, float]:
    if not ring:
        return 0.0, 0.0
    lng = sum(float(p[0]) for p in ring) / len(ring)
    lat = sum(float(p[1]) for p in ring) / len(ring)
    return lat, lng


def _deterministic_jitter(lat: float, lng: float, scale: int = 26) -> int:
    seed = f"{lat:.2f}:{lng:.2f}".encode("utf-8")
    return (sum(seed) % (scale * 2 + 1)) - scale


def _land_color(lat: float, lng: float) -> tuple[int, int, int]:
    """Approximate visible-earth biomes without external imagery."""
    alat = abs(lat)
    desert = (
        (8 <= lat <= 34 and -18 <= lng <= 64)  # Sahara, Sahel, Arabia
        or (-33 <= lat <= -14 and 112 <= lng <= 146)  # Australia interior
        or (-31 <= lat <= -15 and 14 <= lng <= 31)  # Namib/Kalahari
        or (-32 <= lat <= -15 and -78 <= lng <= -65)  # Atacama/Andes dry belt
        or (25 <= lat <= 43 and -125 <= lng <= -98)  # US southwest / Mexico north
        or (30 <= lat <= 47 and 45 <= lng <= 90)  # Central Asia dry belt
    )
    rainforest = -12 <= lat <= 12 and (
        (-82 <= lng <= -45) or (-18 <= lng <= 35) or (90 <= lng <= 155)
    )
    savanna = -18 <= lat <= 18 and not rainforest
    temperate = 25 <= alat <= 58
    ice = alat >= 68 or lat <= -58

    if ice:
        base = (215, 226, 229)
    elif desert:
        base = (190, 141, 76)
    elif rainforest:
        base = (38, 96, 51)
    elif savanna:
        base = (104, 121, 58)
    elif temperate:
        base = (74, 115, 69)
    else:
        base = (99, 105, 70)

    jitter = _deterministic_jitter(lat, lng)
    return tuple(_clamp_channel(c + jitter) for c in base)


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
        lat, lng = _centroid(ring)
        fill = _land_color(lat, lng) if idx == 0 else OCEAN_DEEP
        draw.polygon(pixels, fill=fill, outline=COAST if idx == 0 else None)


def generate(out_path: Path = OUT_PATH, width: int = WIDTH, height: int = HEIGHT) -> Path:
    try:
        from PIL import Image, ImageDraw, ImageFilter
    except ImportError as exc:
        raise SystemExit("Pillow required: pip install Pillow") from exc

    if not GEO_PATH.is_file():
        raise SystemExit(f"missing geo asset: {GEO_PATH}")

    geo = json.loads(GEO_PATH.read_text(encoding="utf-8"))
    img = Image.new("RGB", (width, height), OCEAN_DEEP)
    px = img.load()
    for y in range(height):
        lat_factor = abs((y / max(1, height - 1)) - 0.5) * 2.0
        for x in range(width):
            wave = ((x * 17 + y * 29) % 23) / 22.0
            shelf = max(0.0, 1.0 - lat_factor) * 0.14 + wave * 0.04
            px[x, y] = _mix(OCEAN_DEEP, OCEAN_SHELF, shelf)

    draw = ImageDraw.Draw(img)
    for feat in geo.get("features") or []:
        geom = feat.get("geometry")
        if isinstance(geom, dict):
            _draw_geometry(draw, geom, width, height)

    # A tiny blur removes jagged topojson edges while preserving biome contrast.
    img = img.filter(ImageFilter.GaussianBlur(radius=0.35))
    shade = Image.new("L", (width, height), 0)
    shade_px = shade.load()
    for y in range(height):
        lat_factor = abs((y / max(1, height - 1)) - 0.5) * 2.0
        for x in range(width):
            lon_wave = ((x / max(1, width - 1)) - 0.5) ** 2
            shade_px[x, y] = _clamp_channel((lat_factor * 34) + (lon_wave * 26))
    img = Image.composite(
        Image.new("RGB", (width, height), _mix(OCEAN_DEEP, (0, 0, 0), 0.35)),
        img,
        shade.filter(ImageFilter.GaussianBlur(radius=18)),
    )
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
