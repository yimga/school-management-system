"""Generate brand-monogram PNG icons for the companion-extension Manifest V3.

The MV3 manifest at ``companion-extension/manifest.json`` references
``icons/icon-{16,48,128}.png``. v3.39.0 shipped solid-color placeholders;
v3.40.0 replaces them with a recognizable RMC monogram glyph rendered
from a hand-rolled 5x7 bitmap font table.

Design
------
* Rounded-square background in RMC indigo ``#3A45FF`` (mid-blue).
* Foreground monogram (default ``RMC``) in near-white ``#F4F6FF``.
* 16px size renders just the first glyph (single 5x7 cell), since
  three glyphs at any usable scale do not fit cleanly in 16x16.
* 48px renders all three glyphs at scale=2 (15x7 -> 30x14 pixels).
* 128px renders all three glyphs at scale=5 (75x35 pixels).

Hard constraints
----------------
* Stdlib-only — ``zlib`` + ``struct`` only.
* Runs identically on Windows / Linux / macOS.
* Idempotent: same inputs -> byte-identical output.

CLI
---
::

    python scripts/generate_companion_extension_icons.py [--out DIR] [--monogram RMC]

PNG spec: https://www.w3.org/TR/PNG/.
"""

from __future__ import annotations

import argparse
import pathlib
import struct
import sys
import zlib


REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
DEFAULT_ICONS_DIR = REPO_ROOT / "companion-extension" / "icons"

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"

# RMC indigo brand color (#3A45FF) — slightly more saturated than the
# v3.39 placeholder so the new monogram cards do not look "the same as
# the placeholder, plus letters" when stacked side by side.
RMC_INDIGO = (0x3A, 0x45, 0xFF)
RMC_FOREGROUND = (0xF4, 0xF6, 0xFF)

# Hand-rolled 5x7 bitmap font. Each glyph is a list of seven row
# integers; bits 0..4 are columns left-to-right (MSB-of-the-low-5 =
# leftmost). Only the glyphs we need are defined; unknown letters
# render as a filled block so the failure mode is visible, not silent.
#
# Layout legend (one row, with `1` = ink, `0` = background):
#
#   R:  1 1 1 1 0
#       1 0 0 0 1
#       1 0 0 0 1
#       1 1 1 1 0
#       1 0 1 0 0
#       1 0 0 1 0
#       1 0 0 0 1
GLYPHS_5x7: dict[str, list[int]] = {
    "R": [
        0b11110,
        0b10001,
        0b10001,
        0b11110,
        0b10100,
        0b10010,
        0b10001,
    ],
    "M": [
        0b10001,
        0b11011,
        0b10101,
        0b10101,
        0b10001,
        0b10001,
        0b10001,
    ],
    "C": [
        0b01111,
        0b10000,
        0b10000,
        0b10000,
        0b10000,
        0b10000,
        0b01111,
    ],
    # Defensive fallbacks so a `--monogram FOO` invocation in tests
    # produces a different but still well-formed pixel buffer.
    "F": [
        0b11111,
        0b10000,
        0b10000,
        0b11110,
        0b10000,
        0b10000,
        0b10000,
    ],
    "O": [
        0b01110,
        0b10001,
        0b10001,
        0b10001,
        0b10001,
        0b10001,
        0b01110,
    ],
    "B": [
        0b11110,
        0b10001,
        0b10001,
        0b11110,
        0b10001,
        0b10001,
        0b11110,
    ],
    "A": [
        0b01110,
        0b10001,
        0b10001,
        0b11111,
        0b10001,
        0b10001,
        0b10001,
    ],
}

GLYPH_W = 5
GLYPH_H = 7
GLYPH_KERN = 1  # one blank column between adjacent glyphs at scale=1


def _png_chunk(chunk_type: bytes, data: bytes) -> bytes:
    """Build one PNG chunk: length(4) + type(4) + data + crc32(4)."""
    length = struct.pack(">I", len(data))
    crc = zlib.crc32(chunk_type + data) & 0xFFFFFFFF
    return length + chunk_type + data + struct.pack(">I", crc)


def _encode_png(width: int, height: int, pixels: list[tuple[int, int, int]]) -> bytes:
    """Encode an RGB pixel list as deterministic, level-9 zlib PNG bytes.

    ``pixels`` is row-major, length ``width * height``. Each scanline
    is prefixed with a single ``0x00`` filter byte (filter type None).
    """
    if len(pixels) != width * height:
        raise ValueError("pixel buffer length does not match width*height")

    raw_rows: list[bytes] = []
    for y in range(height):
        row = bytearray()
        row.append(0)  # filter: None
        base = y * width
        for x in range(width):
            r, g, b = pixels[base + x]
            row.append(r)
            row.append(g)
            row.append(b)
        raw_rows.append(bytes(row))
    raw = b"".join(raw_rows)
    compressed = zlib.compress(raw, level=9)

    ihdr = struct.pack(
        ">IIBBBBB",
        width,
        height,
        8,  # bit depth
        2,  # color type: truecolor (RGB)
        0,  # compression method (deflate)
        0,  # filter method (adaptive)
        0,  # interlace method (none)
    )

    return (
        PNG_SIGNATURE
        + _png_chunk(b"IHDR", ihdr)
        + _png_chunk(b"IDAT", compressed)
        + _png_chunk(b"IEND", b"")
    )


def _rounded_mask(size: int, radius: int) -> list[bool]:
    """Return a row-major mask where True = inside the rounded square."""
    mask: list[bool] = []
    for y in range(size):
        for x in range(size):
            # Distance from nearest corner center.
            cx = x
            cy = y
            if x < radius and y < radius:
                dx = radius - 1 - x
                dy = radius - 1 - y
                inside = (dx * dx + dy * dy) <= (radius - 1) * (radius - 1)
            elif x >= size - radius and y < radius:
                dx = x - (size - radius)
                dy = radius - 1 - y
                inside = (dx * dx + dy * dy) <= (radius - 1) * (radius - 1)
            elif x < radius and y >= size - radius:
                dx = radius - 1 - x
                dy = y - (size - radius)
                inside = (dx * dx + dy * dy) <= (radius - 1) * (radius - 1)
            elif x >= size - radius and y >= size - radius:
                dx = x - (size - radius)
                dy = y - (size - radius)
                inside = (dx * dx + dy * dy) <= (radius - 1) * (radius - 1)
            else:
                inside = True
            mask.append(inside)
            del cx, cy  # silence linters; coords already used above
    return mask


def _glyph_bitmap(letter: str) -> list[int]:
    """Return the 5x7 row table for ``letter``; fallback = solid block."""
    return GLYPHS_5x7.get(letter.upper(), [0b11111] * GLYPH_H)


def _stamp_glyph(
    pixels: list[tuple[int, int, int]],
    size: int,
    letter: str,
    origin_x: int,
    origin_y: int,
    scale: int,
    color: tuple[int, int, int],
) -> None:
    """Stamp a single 5x7 glyph onto ``pixels`` in-place at integer scale."""
    rows = _glyph_bitmap(letter)
    for gy in range(GLYPH_H):
        row_bits = rows[gy]
        for gx in range(GLYPH_W):
            # Bit (GLYPH_W - 1 - gx) of row_bits = pixel at gx.
            on = (row_bits >> (GLYPH_W - 1 - gx)) & 1
            if not on:
                continue
            for sy in range(scale):
                py = origin_y + gy * scale + sy
                if py < 0 or py >= size:
                    continue
                for sx in range(scale):
                    px = origin_x + gx * scale + sx
                    if px < 0 or px >= size:
                        continue
                    pixels[py * size + px] = color


def render_monogram_png(size: int, monogram: str) -> bytes:
    """Render a rounded-indigo PNG with the monogram stamped centered.

    16px renders only the FIRST glyph (three glyphs do not fit
    legibly at scale=1 in a 16x16 frame). 48px renders all three at
    scale=2; 128px at scale=5.
    """
    if size <= 0:
        raise ValueError("size must be positive")
    if not monogram:
        raise ValueError("monogram must be a non-empty string")

    # Background: rounded-square indigo.
    radius = max(1, size // 6)
    mask = _rounded_mask(size, radius)
    transparent_bg = (0, 0, 0)  # behind the rounded mask — RGB only (no alpha)
    pixels: list[tuple[int, int, int]] = [
        RMC_INDIGO if inside else transparent_bg for inside in mask
    ]

    # Foreground: scale glyphs based on size class.
    if size <= 20:
        # Single-glyph mode — use just the first character.
        letters = monogram[:1]
        scale = max(1, (size - 4) // GLYPH_H)
    elif size <= 64:
        letters = monogram[:3]
        scale = 2
    else:
        letters = monogram[:3]
        scale = max(3, size // 26)

    n = len(letters)
    glyph_w_scaled = GLYPH_W * scale
    glyph_h_scaled = GLYPH_H * scale
    kern_scaled = max(1, GLYPH_KERN * scale)
    total_w = n * glyph_w_scaled + (n - 1) * kern_scaled
    total_h = glyph_h_scaled

    origin_x0 = (size - total_w) // 2
    origin_y = (size - total_h) // 2

    for i, letter in enumerate(letters):
        ox = origin_x0 + i * (glyph_w_scaled + kern_scaled)
        _stamp_glyph(pixels, size, letter, ox, origin_y, scale, RMC_FOREGROUND)

    return _encode_png(size, size, pixels)


def write_icon(out_dir: pathlib.Path, size: int, monogram: str) -> pathlib.Path:
    """Render and write ``icon-<size>.png`` to ``out_dir``."""
    out_path = out_dir / f"icon-{size}.png"
    data = render_monogram_png(size, monogram)
    out_path.write_bytes(data)
    return out_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate RMC monogram PNG icons for the companion extension.",
    )
    parser.add_argument(
        "--out",
        type=pathlib.Path,
        default=DEFAULT_ICONS_DIR,
        help="Output directory (default: companion-extension/icons/).",
    )
    parser.add_argument(
        "--monogram",
        type=str,
        default="RMC",
        help="Up to 3 letters to render as the brand monogram (default: RMC).",
    )
    args = parser.parse_args(argv)

    out_dir: pathlib.Path = args.out
    out_dir.mkdir(parents=True, exist_ok=True)

    written: list[str] = []
    for size in (16, 48, 128):
        path = write_icon(out_dir, size, args.monogram)
        try:
            rel = path.relative_to(REPO_ROOT)
        except ValueError:
            rel = path
        written.append(f"{rel} ({path.stat().st_size} bytes)")
    for line in written:
        sys.stdout.write(line + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
