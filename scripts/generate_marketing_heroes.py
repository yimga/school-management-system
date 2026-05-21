#!/usr/bin/env python3
"""Generate Apple-tier marketing hero images.

Produces 1600x1000 WebP compositions for each primary marketing page,
matching the editorial cream + terracotta palette established in v2.X. These
are stylized abstract compositions — wash gradients, generous negative space,
thin geometric overlays — that act as photography substitutes while the real
content shoot is pending. They're tenant-recolorable via CSS overlays.

Re-run from the project root:

    python scripts/generate_marketing_heroes.py
"""
from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "static" / "images" / "marketing" / "heroes"

CREAM = (250, 247, 242)
CREAM_DEEP = (236, 228, 216)
INK = (31, 41, 55)
INK_SOFT = (75, 85, 99)
TERRACOTTA = (193, 87, 58)
TERRACOTTA_DEEP = (130, 58, 39)
HAIRLINE = (217, 209, 196)
ACCENT_GLOW = (255, 200, 168)

W, H = 1600, 1000


def _vert_gradient(top: tuple[int, int, int], bottom: tuple[int, int, int]) -> Image.Image:
    """Draw a vertical 2-stop gradient at full canvas size."""
    img = Image.new("RGB", (W, H), top)
    px = img.load()
    for y in range(H):
        t = y / (H - 1)
        r = int(top[0] + (bottom[0] - top[0]) * t)
        g = int(top[1] + (bottom[1] - top[1]) * t)
        b = int(top[2] + (bottom[2] - top[2]) * t)
        for x in range(W):
            px[x, y] = (r, g, b)
    return img


def _radial_glow(center: tuple[int, int], radius: int, color: tuple[int, int, int], alpha_peak: int = 90) -> Image.Image:
    """Soft radial glow as an RGBA overlay."""
    g = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(g)
    cx, cy = center
    # Concentric circles with decaying alpha for a smooth bloom.
    steps = 80
    for i in range(steps, 0, -1):
        r = int(radius * i / steps)
        a = int(alpha_peak * (1 - i / steps) ** 2)
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(*color, a))
    return g.filter(ImageFilter.GaussianBlur(radius=radius // 20))


def _draw_constellation(draw: ImageDraw.ImageDraw, anchors: list[tuple[int, int]], color: tuple[int, int, int]) -> None:
    """Thin connecting lines between anchor points + small terminal dots —
    suggests data flow / connection / structure without being literal."""
    for (x1, y1), (x2, y2) in zip(anchors, anchors[1:]):
        draw.line([(x1, y1), (x2, y2)], fill=(*color, 90), width=1)
    for x, y in anchors:
        draw.ellipse([x - 4, y - 4, x + 4, y + 4], fill=(*color, 200))


def _draw_arc(draw: ImageDraw.ImageDraw, bbox: tuple[int, int, int, int], start: float, end: float, color: tuple[int, int, int], width: int = 2) -> None:
    draw.arc(bbox, start=start, end=end, fill=(*color, 180), width=width)


def _font(path: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(path, size=size)


# ---- compositions per page ----

def compose_home() -> Image.Image:
    """Homepage: warm-cream wash + constellation of school touch-points."""
    base = _vert_gradient(CREAM, CREAM_DEEP)
    base.paste(_radial_glow((W * 3 // 4, H // 3), 700, ACCENT_GLOW, 110), (0, 0), _radial_glow((W * 3 // 4, H // 3), 700, ACCENT_GLOW, 110))
    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(overlay)
    # Constellation suggesting bell hours / interconnected touch-points.
    anchors = [(220, 720), (380, 580), (560, 640), (740, 470), (920, 540), (1140, 410), (1340, 500)]
    _draw_constellation(d, anchors, TERRACOTTA)
    # Single sweeping arc — "the curve of a quiet day."
    _draw_arc(d, (160, 360, 1500, 1180), 200, 340, TERRACOTTA_DEEP, width=2)
    base.paste(overlay, (0, 0), overlay)
    return base


def compose_platform() -> Image.Image:
    """Platform: layered hairline rectangles — quiet system architecture."""
    base = _vert_gradient(CREAM, CREAM_DEEP)
    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(overlay)
    # Six staggered hairline rectangles, each symmetrically inset from center,
    # suggesting platform layers stacked in depth.
    cx, cy = W // 2, H // 2
    for i, (half_w, half_h) in enumerate([(640, 340), (560, 290), (480, 240), (400, 190), (320, 140), (240, 90)]):
        opacity = 200 - i * 25
        d.rounded_rectangle(
            [cx - half_w, cy - half_h, cx + half_w, cy + half_h],
            radius=18,
            outline=(*HAIRLINE, opacity),
            width=1,
        )
    # Single terracotta dot — the "tenant" inside the platform.
    d.ellipse([W // 2 - 12, H // 2 - 12, W // 2 + 12, H // 2 + 12], fill=(*TERRACOTTA, 240))
    base.paste(overlay, (0, 0), overlay)
    return base


def compose_solutions() -> Image.Image:
    """Solutions: six chips arranged in a quiet grid — each kind of school."""
    base = _vert_gradient(CREAM, CREAM_DEEP)
    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(overlay)
    # 3x2 grid of soft chips.
    cols, rows = 3, 2
    chip_w, chip_h = 360, 220
    gap_x, gap_y = 80, 80
    total_w = cols * chip_w + (cols - 1) * gap_x
    total_h = rows * chip_h + (rows - 1) * gap_y
    start_x = (W - total_w) // 2
    start_y = (H - total_h) // 2
    for r in range(rows):
        for c in range(cols):
            x = start_x + c * (chip_w + gap_x)
            y = start_y + r * (chip_h + gap_y)
            d.rounded_rectangle([x, y, x + chip_w, y + chip_h], radius=24, outline=(*HAIRLINE, 200), width=1)
            # Single dot in the corner — accent the one that highlights for this composition.
            if r == 0 and c == 1:
                d.ellipse([x + chip_w - 32, y + 20, x + chip_w - 20, y + 32], fill=(*TERRACOTTA, 230))
    base.paste(overlay, (0, 0), overlay)
    return base


def compose_pricing() -> Image.Image:
    """Pricing: single ascending stair — honest, transparent."""
    base = _vert_gradient(CREAM, CREAM_DEEP)
    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(overlay)
    # One ascending line.
    step_x, step_y = 220, 70
    start_x, start_y = 280, 750
    points: list[tuple[int, int]] = [(start_x, start_y)]
    for i in range(5):
        nx = start_x + (i + 1) * step_x
        ny = start_y - (i + 1) * step_y
        points.append((nx, ny))
    # Draw the stair as a single zig-zag polyline.
    for (x1, y1), (x2, y2) in zip(points, points[1:]):
        d.line([(x1, y1), (x2, y1)], fill=(*HAIRLINE, 220), width=2)
        d.line([(x2, y1), (x2, y2)], fill=(*HAIRLINE, 220), width=2)
    # Terminal dot at the top.
    tx, ty = points[-1]
    d.ellipse([tx - 9, ty - 9, tx + 9, ty + 9], fill=(*TERRACOTTA, 240))
    base.paste(overlay, (0, 0), overlay)
    return base


def compose_why() -> Image.Image:
    """Why: a single bold arc + parallel hairlines — quiet conviction."""
    base = _vert_gradient(CREAM, CREAM_DEEP)
    base.paste(_radial_glow((W // 4, H * 2 // 3), 600, ACCENT_GLOW, 90), (0, 0), _radial_glow((W // 4, H * 2 // 3), 600, ACCENT_GLOW, 90))
    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(overlay)
    # Three parallel hairlines — "five bells, six bells, one quiet system."
    for i in range(3):
        y = 350 + i * 60
        d.line([(200, y), (W - 300, y)], fill=(*HAIRLINE, 180), width=1)
    # Bold terracotta arc — the human curve.
    _draw_arc(d, (200, 100, 1500, 1100), 220, 320, TERRACOTTA, width=3)
    base.paste(overlay, (0, 0), overlay)
    return base


def compose_migrate() -> Image.Image:
    """Migrate: two columns connected by gentle arrows — old system → new."""
    base = _vert_gradient(CREAM, CREAM_DEEP)
    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(overlay)
    # Left column (legacy) — outline only, muted.
    d.rounded_rectangle([260, 280, 600, 720], radius=22, outline=(*HAIRLINE, 220), width=1)
    # Right column (RunMyCampus) — solid hairline + accent dot.
    d.rounded_rectangle([1000, 280, 1340, 720], radius=22, outline=(*HAIRLINE, 240), width=2)
    d.ellipse([1160, 480, 1180, 500], fill=(*TERRACOTTA, 240))
    # Three flowing arrows from left to right.
    for i in range(3):
        y = 380 + i * 120
        d.line([(600, y), (1000, y)], fill=(*HAIRLINE, 200), width=1)
        # Subtle terracotta tip on the middle arrow.
        if i == 1:
            d.polygon([(995, y - 6), (1010, y), (995, y + 6)], fill=(*TERRACOTTA, 220))
    base.paste(overlay, (0, 0), overlay)
    return base


def compose_trust() -> Image.Image:
    """Trust: concentric rings — defense in depth, calm and centered."""
    base = _vert_gradient(CREAM, CREAM_DEEP)
    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(overlay)
    cx, cy = W // 2, H // 2 + 30
    for i, r in enumerate([460, 380, 300, 220, 140]):
        opacity = 80 + i * 30
        d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=(*HAIRLINE, opacity), width=1)
    # Single small terracotta dot at the center.
    d.ellipse([cx - 8, cy - 8, cx + 8, cy + 8], fill=(*TERRACOTTA, 240))
    base.paste(overlay, (0, 0), overlay)
    return base


# ---- driver ----

PAGES: dict[str, callable] = {
    "home":      compose_home,
    "platform":  compose_platform,
    "solutions": compose_solutions,
    "pricing":   compose_pricing,
    "why":       compose_why,
    "migrate":   compose_migrate,
    "trust":     compose_trust,
}


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    written = 0
    total_bytes = 0
    for slug, composer in PAGES.items():
        img = composer()
        out_webp = OUT_DIR / f"hero-{slug}.webp"
        img.save(out_webp, format="WEBP", quality=82, method=6)
        # Also write a JPEG fallback for older social crawlers.
        out_jpg = OUT_DIR / f"hero-{slug}.jpg"
        img.save(out_jpg, format="JPEG", quality=86, optimize=True)
        written += 2
        total_bytes += out_webp.stat().st_size + out_jpg.stat().st_size
        print(f"  hero-{slug}: webp {out_webp.stat().st_size:,}B  + jpg {out_jpg.stat().st_size:,}B")
    print(f"\nWrote {written} hero files, total {total_bytes:,} bytes")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except FileNotFoundError as e:
        print(f"error: required font missing: {e}", file=sys.stderr)
        sys.exit(1)
