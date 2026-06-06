#!/usr/bin/env python
"""Generate PLACEHOLDER-SAFE, on-brand marketing image assets (stdlib-only).

These files are referenced by the marketing templates but were missing from
``static/`` (the render-safety gate flagged them), so social-share previews and
PWA icons were broken:

    * ``static/images/runmycampus-og-card.png``  (og:image / twitter:image)
    * ``static/images/icon-192.png``             (PWA icon)
    * ``static/images/icon-512.png``             (PWA icon, larger)

This writes tasteful, on-brand PLACEHOLDERS — RunMyCampus wordmark + a simple
geometric mark on the brand indigo, with a tagline on the OG card. There are NO
photos, NO people, and NO fabricated third-party logos. They exist purely so the
share card and icons are valid + on-brand until final brand art replaces them.

Swap freely: drop real PNGs at the same paths and delete/ignore this generator.

Pure standard library (``zlib`` + ``struct``) — no Pillow, mirroring
``scripts/generate_companion_extension_icons.py``.

Run:  python scripts/generate_marketing_brand_assets.py
"""

from __future__ import annotations

import struct
import zlib
from pathlib import Path

# Brand palette (placeholder; mirrors the platform indigo).
INDIGO = (79, 70, 229)        # #4F46E5  off-token-allow: placeholder-brand-asset-generator
INDIGO_DEEP = (49, 46, 129)   # #312E81  deep panel
INK = (15, 23, 42)            # #0F172A
WHITE = (255, 255, 255)
MIST = (199, 210, 254)        # #C7D2FE  soft accent text

REPO = Path(__file__).resolve().parents[1]
OUT_DIR = REPO / "static" / "images"

# --- minimal 5x7 uppercase font (rows top->bottom, '#' = on) ----------------
# Imperfect glyphs are acceptable: these are explicitly swappable placeholders.
_FONT: dict[str, tuple[str, ...]] = {
    " ": ("     ", "     ", "     ", "     ", "     ", "     ", "     "),
    "A": (" ### ", "#   #", "#   #", "#####", "#   #", "#   #", "#   #"),
    "B": ("#### ", "#   #", "#### ", "#   #", "#   #", "#   #", "#### "),
    "C": (" ####", "#    ", "#    ", "#    ", "#    ", "#    ", " ####"),
    "D": ("#### ", "#   #", "#   #", "#   #", "#   #", "#   #", "#### "),
    "E": ("#####", "#    ", "#### ", "#    ", "#    ", "#    ", "#####"),
    "F": ("#####", "#    ", "#### ", "#    ", "#    ", "#    ", "#    "),
    "G": (" ####", "#    ", "#    ", "#  ##", "#   #", "#   #", " ####"),
    "H": ("#   #", "#   #", "#   #", "#####", "#   #", "#   #", "#   #"),
    "I": ("#####", "  #  ", "  #  ", "  #  ", "  #  ", "  #  ", "#####"),
    "J": ("  ###", "   # ", "   # ", "   # ", "#  # ", "#  # ", " ##  "),
    "K": ("#   #", "#  # ", "# #  ", "##   ", "# #  ", "#  # ", "#   #"),
    "L": ("#    ", "#    ", "#    ", "#    ", "#    ", "#    ", "#####"),
    "M": ("#   #", "## ##", "# # #", "#   #", "#   #", "#   #", "#   #"),
    "N": ("#   #", "##  #", "# # #", "#  ##", "#   #", "#   #", "#   #"),
    "O": (" ### ", "#   #", "#   #", "#   #", "#   #", "#   #", " ### "),
    "P": ("#### ", "#   #", "#   #", "#### ", "#    ", "#    ", "#    "),
    "Q": (" ### ", "#   #", "#   #", "#   #", "# # #", "#  # ", " ## #"),
    "R": ("#### ", "#   #", "#   #", "#### ", "# #  ", "#  # ", "#   #"),
    "S": (" ####", "#    ", "#    ", " ### ", "    #", "    #", "#### "),
    "T": ("#####", "  #  ", "  #  ", "  #  ", "  #  ", "  #  ", "  #  "),
    "U": ("#   #", "#   #", "#   #", "#   #", "#   #", "#   #", " ### "),
    "V": ("#   #", "#   #", "#   #", "#   #", "#   #", " # # ", "  #  "),
    "W": ("#   #", "#   #", "#   #", "#   #", "# # #", "## ##", "#   #"),
    "X": ("#   #", "#   #", " # # ", "  #  ", " # # ", "#   #", "#   #"),
    "Y": ("#   #", "#   #", " # # ", "  #  ", "  #  ", "  #  ", "  #  "),
    "Z": ("#####", "    #", "   # ", "  #  ", " #   ", "#    ", "#####"),
    "0": (" ### ", "#   #", "#  ##", "# # #", "##  #", "#   #", " ### "),
    "1": ("  #  ", " ##  ", "  #  ", "  #  ", "  #  ", "  #  ", "#####"),
    "2": (" ### ", "#   #", "    #", "   # ", "  #  ", " #   ", "#####"),
    "3": ("#####", "   # ", "  #  ", "   # ", "    #", "#   #", " ### "),
    "4": ("   # ", "  ## ", " # # ", "#  # ", "#####", "   # ", "   # "),
    "5": ("#####", "#    ", "#### ", "    #", "    #", "#   #", " ### "),
    "6": (" ### ", "#    ", "#    ", "#### ", "#   #", "#   #", " ### "),
    "7": ("#####", "    #", "   # ", "  #  ", " #   ", " #   ", " #   "),
    "8": (" ### ", "#   #", "#   #", " ### ", "#   #", "#   #", " ### "),
    "9": (" ### ", "#   #", "#   #", " ####", "    #", "    #", " ### "),
    ".": ("     ", "     ", "     ", "     ", "     ", "  ## ", "  ## "),
    "-": ("     ", "     ", "     ", "#####", "     ", "     ", "     "),
    "·": ("     ", "     ", "  #  ", " ### ", "  #  ", "     ", "     "),
}

_GLYPH_W = 5
_GLYPH_H = 7


class Canvas:
    """A tiny RGB raster with rectangle + scaled-text drawing."""

    def __init__(self, width: int, height: int, bg: tuple[int, int, int]):
        self.w = width
        self.h = height
        self.px = bytearray()
        row = bytes(bg) * width
        for _ in range(height):
            self.px += row

    def _set(self, x: int, y: int, color: tuple[int, int, int]) -> None:
        if 0 <= x < self.w and 0 <= y < self.h:
            i = (y * self.w + x) * 3
            self.px[i : i + 3] = bytes(color)

    def rect(self, x: int, y: int, w: int, h: int, color: tuple[int, int, int]) -> None:
        for yy in range(y, y + h):
            for xx in range(x, x + w):
                self._set(xx, yy, color)

    def text(
        self,
        s: str,
        x: int,
        y: int,
        scale: int,
        color: tuple[int, int, int],
        spacing: int = 1,
    ) -> int:
        """Draw ``s`` (uppercased) at (x, y); returns the x cursor after it."""
        cx = x
        for ch in s.upper():
            glyph = _FONT.get(ch, _FONT[" "])
            for ry, rowbits in enumerate(glyph):
                for rx, bit in enumerate(rowbits):
                    if bit == "#":
                        self.rect(
                            cx + rx * scale, y + ry * scale, scale, scale, color
                        )
            cx += (_GLYPH_W + spacing) * scale
        return cx

    def text_width(self, s: str, scale: int, spacing: int = 1) -> int:
        return len(s) * (_GLYPH_W + spacing) * scale

    def text_centered(
        self, s: str, cx: int, y: int, scale: int, color: tuple[int, int, int]
    ) -> None:
        w = self.text_width(s, scale)
        self.text(s, cx - w // 2, y, scale, color)

    def to_png(self) -> bytes:
        # Add the per-row filter byte (0 = None) required by the PNG spec.
        raw = bytearray()
        stride = self.w * 3
        for y in range(self.h):
            raw.append(0)
            raw += self.px[y * stride : (y + 1) * stride]
        compressed = zlib.compress(bytes(raw), 9)

        def chunk(tag: bytes, data: bytes) -> bytes:
            return (
                struct.pack(">I", len(data))
                + tag
                + data
                + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
            )

        sig = b"\x89PNG\r\n\x1a\n"
        ihdr = struct.pack(">IIBBBBB", self.w, self.h, 8, 2, 0, 0, 0)  # 8-bit RGB
        return sig + chunk(b"IHDR", ihdr) + chunk(b"IDAT", compressed) + chunk(b"IEND", b"")


def _draw_monogram(c: Canvas, x: int, y: int, size: int) -> None:
    """A simple white rounded-square tile with an indigo 'R' — the brand mark."""
    c.rect(x, y, size, size, WHITE)
    # trim corners for a soft-rounded feel
    corner = max(2, size // 10)
    for cx, cy in ((x, y), (x + size - corner, y), (x, y + size - corner),
                   (x + size - corner, y + size - corner)):
        c.rect(cx, cy, corner, corner, INDIGO)
    scale = max(2, size // 9)
    gw = _GLYPH_W * scale
    gh = _GLYPH_H * scale
    c.text("R", x + (size - gw) // 2, y + (size - gh) // 2, scale, INDIGO)


def make_og_card() -> Canvas:
    c = Canvas(1200, 630, INDIGO)
    # deep band along the bottom for contrast
    c.rect(0, 470, 1200, 160, INDIGO_DEEP)
    _draw_monogram(c, 90, 90, 150)
    c.text("RUNMYCAMPUS", 280, 120, 11, WHITE)
    c.text("THE OPERATING SYSTEM FOR MODERN SCHOOLS", 92, 300, 5, MIST)
    c.text("ADMISSIONS · FEES · ATTENDANCE · OFFLINE-FIRST", 92, 520, 4, WHITE)
    return c


def make_icon(size: int) -> Canvas:
    c = Canvas(size, size, INDIGO)
    pad = size // 6
    _draw_monogram(c, pad, pad, size - 2 * pad)
    return c


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    targets = {
        "runmycampus-og-card.png": make_og_card(),
        "icon-192.png": make_icon(192),
        "icon-512.png": make_icon(512),
    }
    for name, canvas in targets.items():
        data = canvas.to_png()
        path = OUT_DIR / name
        path.write_bytes(data)
        assert data[:8] == b"\x89PNG\r\n\x1a\n", f"{name} is not a valid PNG"
        print(f"wrote {path.relative_to(REPO)}  ({len(data)} bytes, {canvas.w}x{canvas.h})")

    readme = OUT_DIR / "README-brand-placeholders.md"
    readme.write_text(
        "# Marketing brand placeholders\n\n"
        "`runmycampus-og-card.png`, `icon-192.png`, `icon-512.png` are "
        "**placeholder** assets generated by `scripts/generate_marketing_brand_assets.py` "
        "(stdlib-only, on-brand indigo + wordmark, no photos/people/third-party logos).\n\n"
        "Replace them with final brand art at the same paths anytime; the generator "
        "can then be deleted or kept for regenerating placeholders.\n",
        encoding="utf-8",
    )
    print(f"wrote {readme.relative_to(REPO)}")


if __name__ == "__main__":
    main()
