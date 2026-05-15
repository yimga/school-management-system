#!/usr/bin/env python3
"""Generate Open Graph social-share cards.

Produces 1200x630 PNGs matching the marketing surface's editorial palette
(cream background, terracotta accent, Georgia serif headline, Segoe UI Bold
wordmark). The default card lives at `static/images/runmycampus-og-card.png`
and is the fallback used by `templates/partials/rmc_social_meta.html`.

v2.29 (2026-05-15) added per-page covers — pass `--all` to generate covers
for every primary marketing page (platform, solutions, pricing, why,
migrate, trust). Pages whose view sets `og_image` in the context will use
those instead of the platform fallback.

Re-run from the project root:

    python scripts/generate_og_card.py            # platform fallback only
    python scripts/generate_og_card.py --all      # + per-page covers
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "static" / "images"

CREAM = (250, 247, 242)
INK = (31, 41, 55)
INK_SOFT = (75, 85, 99)
TERRACOTTA = (193, 87, 58)
HAIRLINE = (217, 209, 196)

W, H = 1200, 630
GUTTER = W // 12


def _font(path: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(path, size=size)


def _wrap(draw: ImageDraw.ImageDraw, text: str, font, max_w: int) -> list[str]:
    words = text.split()
    lines: list[str] = []
    cur = ""
    for w in words:
        trial = (cur + " " + w).strip()
        bbox = draw.textbbox((0, 0), trial, font=font)
        width = bbox[2] - bbox[0]
        if width <= max_w or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def build_card(out_path: Path, *, chapter: str, eyebrow: str, headline: list[str], subline: str, url_label: str = "runmycampus.com") -> None:
    img = Image.new("RGB", (W, H), CREAM)
    draw = ImageDraw.Draw(img)

    # Rail
    rail_x = W * 2 // 3 + 40
    draw.line([(rail_x, GUTTER), (rail_x, H - GUTTER)], fill=HAIRLINE, width=1)

    # Wordmark
    wm_font = _font("C:/Windows/Fonts/segoeuib.ttf", 38)
    draw.text((GUTTER, GUTTER), "RunMyCampus", font=wm_font, fill=TERRACOTTA)
    bar_y = GUTTER + 60
    draw.rectangle([GUTTER, bar_y, GUTTER + 72, bar_y + 4], fill=TERRACOTTA)

    # Headline
    hl_font = _font("C:/Windows/Fonts/georgiab.ttf", 64)
    y = GUTTER + 120
    for line in headline:
        draw.text((GUTTER, y), line, font=hl_font, fill=INK)
        y += 78

    # Subline
    sub_font = _font("C:/Windows/Fonts/segoeui.ttf", 26)
    draw.text((GUTTER, y + 16), subline, font=sub_font, fill=INK_SOFT)

    # Chapter mark on the right rail
    chap_label_font = _font("C:/Windows/Fonts/constanb.ttf", 22)
    chap_body_font = _font("C:/Windows/Fonts/constan.ttf", 22)
    rail_label_x = rail_x + 40
    draw.text((rail_label_x, GUTTER), chapter, font=chap_label_font, fill=TERRACOTTA)
    draw.text((rail_label_x, GUTTER + 36), eyebrow, font=chap_body_font, fill=INK)

    # Bottom anchor
    url_font = _font("C:/Windows/Fonts/segoeuib.ttf", 22)
    draw.ellipse([GUTTER, H - GUTTER + 6, GUTTER + 10, H - GUTTER + 16], fill=TERRACOTTA)
    draw.text((GUTTER + 22, H - GUTTER), url_label, font=url_font, fill=INK)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path, format="PNG", optimize=True)
    print(f"Wrote {out_path.relative_to(ROOT)} ({out_path.stat().st_size:,} bytes)")


# Per-page composition table.
PAGE_CARDS: list[dict] = [
    {
        "out": "runmycampus-og-card.png",  # platform fallback
        "chapter": "Chapter 01",
        "eyebrow": "The platform",
        "headline": ["Run your school", "the way your school", "actually runs."],
        "subline": "Admissions · academics · finance · parents — one calm platform.",
    },
    {
        "out": "og/og-platform.png",
        "chapter": "Chapter 02",
        "eyebrow": "The platform",
        "headline": ["One quiet system", "behind everything", "your school does."],
        "subline": "Admissions, classrooms, fees, communications — connected, never crowded.",
    },
    {
        "out": "og/og-solutions.png",
        "chapter": "Chapter 03",
        "eyebrow": "By role",
        "headline": ["Built for every", "kind of school", "that exists."],
        "subline": "K–12 · international · networks · faith-based · day · low-connectivity.",
    },
    {
        "out": "og/og-pricing.png",
        "chapter": "Chapter 04",
        "eyebrow": "Pricing",
        "headline": ["Honest pricing.", "No surprise lines.", "No hidden seats."],
        "subline": "One platform fee. Every module. Every student. Every term.",
    },
    {
        "out": "og/og-why.png",
        "chapter": "Chapter 05",
        "eyebrow": "Why us",
        "headline": ["Schools that ran", "louder, finally", "got quiet."],
        "subline": "The day after RunMyCampus is the day your school sounds like a school again.",
    },
    {
        "out": "og/og-migrate.png",
        "chapter": "Chapter 06",
        "eyebrow": "Migration",
        "headline": ["From any system.", "In weeks, not", "academic terms."],
        "subline": "Universal intake. Real ontology. Eight weeks from PowerSchool, FACTS, anything.",
    },
    {
        "out": "og/og-trust.png",
        "chapter": "Chapter 07",
        "eyebrow": "Trust",
        "headline": ["The boring", "engineering you", "want underneath."],
        "subline": "SOC 2 in flight · RLS-enforced isolation · pentested · audit logs from day one.",
    },
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true", help="Generate all per-page covers, not just the platform fallback")
    args = ap.parse_args()

    cards = PAGE_CARDS if args.all else PAGE_CARDS[:1]
    for c in cards:
        build_card(
            OUT_DIR / c["out"],
            chapter=c["chapter"],
            eyebrow=c["eyebrow"],
            headline=c["headline"],
            subline=c["subline"],
        )
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except FileNotFoundError as e:
        print(f"error: required font missing: {e}", file=sys.stderr)
        sys.exit(1)
