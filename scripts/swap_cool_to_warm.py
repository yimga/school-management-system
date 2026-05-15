#!/usr/bin/env python3
"""Mechanical cool→warm hex swap for the v2.45 platform-wide warm sweep.

Replaces hardcoded cool slate / cool indigo / cool blue / apple-cool gray
literals with their warm-bright equivalents across CSS and HTML files.

PRESERVES:
  - `--school-primary` / `--brand-gradient-end` fallback hex (those are
    tenant brand color overridable via RuntimeDefaults — cool here is
    the platform default, not aesthetic intent). Configurable per
    tenant; swapping them would break brand cascade.
  - Files containing 'design-tokens.css' (the SOT — base values).
  - Files under vendor/, node_modules/, staticfiles/.

USAGE:
    python scripts/swap_cool_to_warm.py            # dry-run, print findings
    python scripts/swap_cool_to_warm.py --apply    # write changes
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Cool → Warm hex map. Preserves intent (dark cool → dark warm; light
# cool → light warm). Slate-tier maps to warm-graphite equivalents.
# Apple-cool maps to platform warm-bright defaults.
HEX_SWAP: dict[str, str] = {
    # Slate (cool blue-gray)
    "#020617": "#0d0a07",                          # slate-950 → warm charcoal-deep
    "#0f172a": "#1a1612",                          # slate-900 → warm charcoal
    "#1e293b": "#241e18",                          # slate-800 → warm dark cocoa
    "#334155": "#2c241d",                          # slate-700 → warm cocoa
    "#475569": "#544d44",                          # slate-600 → warm taupe-dark
    "#64748b": "#857c70",                          # slate-500 → warm gray-tan
    "#94a3b8": "#a8a092",                          # slate-400 → warm tan
    "#cbd5e1": "#d9d0c2",                          # slate-300 → warm taupe-light
    "#e2e8f0": "#ede4d6",                          # slate-200 → warm parchment border
    "#f1f5f9": "#f5eedd",                          # slate-100 → honey-cream
    "#f8fafc": "#fffaf0",                          # slate-50 → warm ivory
    # Apple cool grays
    "#0a0a0c": "#1a1612",                          # apple-cool deep → warm charcoal
    "#1c1c1e": "#241e18",                          # apple-cool canvas → warm dark cocoa
    "#2c2c2e": "#2c241d",                          # apple-cool elevated → warm cocoa
    "#f5f5f7": "#fdf9f2",                          # apple-cool bg → buttermilk
    "#fbfbfd": "#fffaf0",                          # apple-cool canvas-light → warm ivory
    # Cool blue (NOT tenant brand — pure decoration)
    "#3b82f6": "#c47f1c",                          # blue-500 → honey
    "#2563eb": "#c47f1c",                          # blue-600 → honey
    "#1d4ed8": "#a06814",                          # blue-700 → deep honey
    # Cool blue-tint hairlines that appeared in reports / receipts
    "#dde1e8": "rgba(80, 55, 25, 0.12)",
    "#e0e2e9": "rgba(80, 55, 25, 0.12)",
    "#e0e4ec": "rgba(80, 55, 25, 0.10)",
    "#e6e6e9": "rgba(80, 55, 25, 0.10)",
    "#cbd5f5": "rgba(80, 55, 25, 0.12)",
    "#d8dee4": "rgba(80, 55, 25, 0.10)",
    "#e1e6ef": "rgba(80, 55, 25, 0.10)",
    "#f0f4fb": "#fffaf0",
    "#f0f3fb": "#fffaf0",
    "#f8f9fb": "#fdf9f2",
    "#f7f8fb": "#fdf9f2",
    # Cool decorative indigo variants (NOT the brand `--school-primary` itself)
    "#a5b4fc": "#e6a052",                          # indigo-300 → honey-light
    "#818cf8": "#c47f1c",                          # indigo-400 → honey
    "#6366f1": "#c47f1c",                          # indigo-500 → honey
    "#4338ca": "#a06814",                          # indigo-700 → deep honey
}

# rgba slate variants — found in shadows and overlays
RGBA_SWAP: list[tuple[str, str]] = [
    (r"rgba\(\s*15\s*,\s*23\s*,\s*42\s*,", "rgba(26, 22, 18,"),         # slate-900 rgba → warm charcoal
    (r"rgba\(\s*30\s*,\s*41\s*,\s*59\s*,", "rgba(36, 30, 24,"),         # slate-800 rgba → warm dark cocoa
    (r"rgba\(\s*51\s*,\s*65\s*,\s*85\s*,", "rgba(44, 36, 29,"),         # slate-700 rgba → warm cocoa
    (r"rgba\(\s*148\s*,\s*163\s*,\s*184\s*,", "rgba(168, 160, 146,"),   # slate-400 rgba → warm tan
    (r"rgba\(\s*100\s*,\s*116\s*,\s*139\s*,", "rgba(133, 124, 112,"),   # slate-500 rgba → warm gray-tan
]

EXCLUDE_FILES = {
    "design-tokens.css",
    "design-tokens-luxury.css",     # second SOT layer; warm cascade depends on its values
    "rmc-warm-bright-school.css",   # the warm layer itself; fallback hex are intentional
    "swap_cool_to_warm.py",
}
EXCLUDE_DIR_PARTS = {"vendor", "node_modules", "staticfiles", "migrations"}

# Files that contain `--school-primary` / `--brand-gradient` token
# DEFINITIONS or tenant-overridable hex — these need extra-careful
# review, so we don't auto-swap them. Manual fixes only.
SKIP_TENANT_BRAND_FILES = {
    # base.html etc. typically only consume vars, but if a template
    # has inline `style="background: #4f46e5"` we want a separate audit.
}


def scan_file(path: Path) -> tuple[str, str, int]:
    """Return (original, modified, count) for a file."""
    try:
        src = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return ("", "", 0)
    modified = src
    swaps = 0

    # 1. Direct hex swaps (case-insensitive)
    for cool, warm in HEX_SWAP.items():
        # Match the hex literal in any case, only when bounded by non-hex chars
        pattern = re.compile(re.escape(cool), re.IGNORECASE)
        new_text, n = pattern.subn(warm, modified)
        if n:
            modified = new_text
            swaps += n

    # 2. rgba slate variants
    for pattern, repl in RGBA_SWAP:
        new_text, n = re.subn(pattern, repl, modified)
        if n:
            modified = new_text
            swaps += n

    return (src, modified, swaps)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="Write changes to disk")
    args = ap.parse_args()

    scan_roots = [
        ROOT / "static" / "css",
        ROOT / "static" / "marketing" / "css",
        ROOT / "templates",
    ]

    total_swaps = 0
    files_changed = 0
    files_visited = 0

    for root in scan_roots:
        if not root.exists():
            continue
        for ext in ("*.css", "*.html"):
            for path in root.rglob(ext):
                if path.name in EXCLUDE_FILES:
                    continue
                if any(part in EXCLUDE_DIR_PARTS for part in path.parts):
                    continue
                files_visited += 1
                src, modified, swaps = scan_file(path)
                if swaps == 0:
                    continue
                total_swaps += swaps
                files_changed += 1
                rel = path.relative_to(ROOT).as_posix()
                if args.apply:
                    path.write_text(modified, encoding="utf-8")
                    print(f"  {swaps:>3}x  {rel}  (written)")
                else:
                    print(f"  {swaps:>3}x  {rel}  (dry-run)")

    print()
    print(f"Files visited: {files_visited}")
    print(f"Files {'changed' if args.apply else 'would change'}: {files_changed}")
    print(f"Total cool->warm {'swaps' if args.apply else 'candidate swaps'}: {total_swaps}")
    if not args.apply:
        print("\nRun with --apply to write changes.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
