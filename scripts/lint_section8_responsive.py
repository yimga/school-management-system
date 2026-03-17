#!/usr/bin/env python3
"""
§8.0.6 Responsive layout and fluid UI — lint for fixed pixel dimensions in layout.

RUNMYCAMPUS SOT §8.0.6: "Remove any fixed width or height in pixels for layout-defining
elements." This script scans CSS (and optionally inline styles in templates) for
fixed px dimensions that often cause non-responsive layout. Reports file:line for
manual review. Use --strict to exit 1 when any violation is found.

Symptom → subsection: "Not responsive / horizontal scroll / fixed width" → §8.0.6.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATIC_CSS = ROOT / "static" / "css"
TEMPLATES = ROOT / "templates"

# Minimum px value to report (SOT §8.0.6: layout-defining elements; icon/small fixed sizes allowed)
DEFAULT_MIN_PX = 100


def scan_css_file(path: Path, min_px: int) -> list[tuple[int, str, str]]:
    """Return list of (line_no, line_stripped, match_reason) for likely layout violations."""
    violations: list[tuple[int, str, str]] = []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    # Match width/height/min-width/min-height: <value>px and capture the number
    pattern = re.compile(
        r"\b(width|height|min-width|min-height)\s*:\s*[^;]*?\b(\d+)\s*px",
        re.IGNORECASE,
    )
    for i, line in enumerate(text.splitlines(), 1):
        stripped = line.strip()
        if not stripped or stripped.startswith("/*"):
            continue
        if "max-width" in stripped or "max-height" in stripped:
            continue
        for m in pattern.finditer(stripped):
            prop, num_str = m.group(1), m.group(2)
            num = int(num_str)
            if num >= min_px:
                violations.append(
                    (i, stripped[:100], f"{prop}: {num}px (layout? prefer rem/%/clamp per §8.0.6)")
                )
                break
    return violations


def scan_css_dir(dir_path: Path, min_px: int) -> dict[Path, list[tuple[int, str, str]]]:
    """Scan all .css under dir_path. Return map path -> violations."""
    results: dict[Path, list[tuple[int, str, str]]] = {}
    if not dir_path.is_dir():
        return results
    for path in sorted(dir_path.rglob("*.css")):
        v = scan_css_file(path, min_px)
        if v:
            results[path] = v
    return results


def main() -> int:
    ap = argparse.ArgumentParser(description="§8.0.6 responsive lint: find fixed px layout dimensions")
    ap.add_argument("--strict", action="store_true", help="Exit 1 if any violation found")
    ap.add_argument("--min-px", type=int, default=DEFAULT_MIN_PX, help=f"Report px >= this (default {DEFAULT_MIN_PX}, layout-sized)")
    ap.add_argument("--dir", type=Path, default=STATIC_CSS, help="CSS directory to scan (default: static/css)")
    args = ap.parse_args()
    css_dir = args.dir.resolve() if args.dir.is_absolute() else ROOT / args.dir
    results = scan_css_dir(css_dir, args.min_px)
    total = sum(len(v) for v in results.values())
    for path in sorted(results.keys()):
        rel = path.relative_to(ROOT)
        for line_no, line, reason in results[path]:
            print(f"{rel}:{line_no}: {reason}")
            print(f"  {line}")
    if total > 0:
        print(f"\n§8.0.6 responsive lint: {total} potential fixed-px layout issue(s) in {len(results)} file(s)")
        print("Consider: rem, em, %, clamp(), or minmax() for layout (SOT §8.0.6).")
        if args.strict:
            return 1
    else:
        print("§8.0.6 responsive lint: no obvious fixed-px layout issues found.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
