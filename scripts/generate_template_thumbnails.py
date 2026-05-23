"""Wave C-4 — generate 75 SVG thumbnails for ExperienceTemplate catalog.

Reads the registry from ``apps.brand_experience.experience_templates.OVERLAYS``
and emits one SVG per template under ``static/img/template-thumbs/<key>.svg``.

Each thumbnail is a 320x200 SVG with:
  - palette-family-anchor background
  - layout-family-derived block schematic (mimics the layout structure)
  - template key + category badge text

Idempotent — safe to re-run. Each SVG embeds no external references and uses
the palette-family hex anchors so thumbnails are self-contained.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

PALETTE_HEX = {
    "editorial-cream":  ("#faf7f0", "#2b2618", "#6b5f4a", "#e5dcc4", "#f5eee0"),
    "warm-terracotta":  ("#fbf5ef", "#3a1f12", "#7d4d2f", "#e7c6a8", "#f3d8c0"),
    "cool-indigo":      ("#f5f6fb", "#14192f", "#4a527d", "#c4cae6", "#d6dbf1"),
    "green-emerald":    ("#f3faf6", "#0e2a1a", "#3f6f53", "#bbd9c6", "#cae8d6"),
    "desert-amber":     ("#fbf6ec", "#3a2912", "#7d5f2f", "#e3ce98", "#f0dab0"),
    "monsoon-teal":     ("#f0f9fa", "#0a2628", "#2f6e72", "#b8d8d9", "#c0e3e3"),
    "sakura-blush":     ("#fbf6f7", "#2c1820", "#7a4a55", "#e6c4cc", "#f0d6db"),
    "andes-clay":       ("#faf3ed", "#3a230f", "#7d5a30", "#d9b58a", "#ecc8a9"),
    "savanna-ochre":    ("#fbf6e6", "#3a2f10", "#7d6628", "#d8c178", "#ecd687"),
    "nordic-slate":     ("#f4f5f7", "#181b22", "#535965", "#c6ccd5", "#d3d8df"),
}


def _layout_blocks(layout_family: int) -> list[tuple[int, int, int, int]]:
    """Return rectangle (x, y, w, h) tuples in 320x200 viewport approximating the layout."""
    if layout_family == 1:  # executive-command — hero strip + 4-quadrant + audit rail
        return [(16, 16, 288, 32), (16, 56, 132, 60), (164, 56, 140, 28), (164, 88, 140, 28), (16, 124, 288, 60)]
    if layout_family == 2:  # academic-operations — timetable + rosters + heat + queue
        return [(16, 16, 288, 24), (16, 48, 80, 136), (104, 48, 200, 64), (104, 120, 96, 64), (208, 120, 96, 64)]
    if layout_family == 3:  # finance-control — waterfall + rail + queue + anchor
        return [(16, 16, 288, 56), (16, 80, 188, 64), (212, 80, 92, 64), (16, 152, 288, 32)]
    if layout_family == 4:  # family-engagement — carousel + river + payment + week
        return [(16, 16, 288, 48), (16, 72, 188, 112), (212, 72, 92, 56), (212, 136, 92, 48)]
    if layout_family == 5:  # teacher-productivity — today + fast + comms + risk
        return [(16, 16, 288, 28), (16, 52, 144, 132), (168, 52, 136, 64), (168, 124, 136, 60)]
    if layout_family == 6:  # student-progress — schedule + kanban + grade + path
        return [(16, 16, 288, 24), (16, 48, 184, 80), (208, 48, 96, 80), (16, 136, 288, 48)]
    if layout_family == 7:  # migration-readiness — stages + impact + checklist + rollback
        return [(16, 16, 288, 32), (16, 56, 132, 128), (164, 56, 140, 64), (164, 128, 140, 56)]
    if layout_family == 8:  # security-compliance — SLO + chain + matrix + incidents
        return [(16, 16, 288, 32), (16, 56, 92, 60), (116, 56, 92, 60), (216, 56, 88, 60), (16, 124, 288, 60)]
    if layout_family == 9:  # low-connectivity-compact — single column flow
        return [(16, 16, 288, 32), (16, 56, 288, 32), (16, 96, 288, 32), (16, 136, 288, 48)]
    if layout_family == 10:  # premium-international — editorial hero + multilingual + admissions + alumni
        return [(16, 16, 288, 60), (16, 84, 192, 100), (216, 84, 88, 60), (216, 152, 88, 32)]
    return [(16, 16, 288, 32), (16, 56, 288, 128)]


def _esc(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def render_svg(*, key: str, category: str, layout_family: int, palette_family: str) -> str:
    bg, ink, ink_secondary, hairline, surface_pop = PALETTE_HEX.get(
        palette_family, PALETTE_HEX["nordic-slate"]
    )
    blocks = _layout_blocks(layout_family)
    block_svg = "".join(
        f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="4" fill="{surface_pop}" stroke="{hairline}" stroke-width="1"/>'
        for (x, y, w, h) in blocks
    )
    label = _esc(key)
    cat = _esc(category)
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 320 200" width="320" height="200" role="img" aria-label="{label}">'
        f'  <rect width="320" height="200" fill="{bg}"/>'
        f'  {block_svg}'
        f'  <text x="16" y="194" font-family="-apple-system, system-ui, sans-serif" font-size="8" fill="{ink_secondary}">{cat}</text>'
        f'  <text x="304" y="194" text-anchor="end" font-family="-apple-system, system-ui, sans-serif" font-size="8" fill="{ink}">{label}</text>'
        f'</svg>'
    )


def main() -> int:
    here = Path(__file__).resolve().parent
    repo_root = here.parent
    sys.path.insert(0, str(repo_root))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    import django

    django.setup()
    from apps.brand_experience import experience_templates as et

    out_dir = repo_root / "static" / "img" / "template-thumbs"
    out_dir.mkdir(parents=True, exist_ok=True)
    written = 0
    for o in et.OVERLAYS:
        svg = render_svg(
            key=o.key,
            category=o.category,
            layout_family=o.layout_family,
            palette_family=o.palette_family,
        )
        target = out_dir / f"{o.key}.svg"
        target.write_text(svg, encoding="utf-8")
        written += 1
    print(f"TEMPLATE_THUMBNAILS_PASS ({written}/{len(et.OVERLAYS)} thumbnails written to {out_dir})")
    return 0 if written == len(et.OVERLAYS) else 1


if __name__ == "__main__":
    sys.exit(main())
