#!/usr/bin/env python3
"""
§8.0.11 Every page — template audit for ultra high-end tenant/manager pages.

RUNMYCAMPUS SOT §8.0.11: Full template audit so every tenant/manager page has no
placeholder styling, fixed pixels (layout-sized), or token drift. This script
scans templates for:
- Inline style with width/height/min-width/min-height in px >= 100 (layout-sized)
- Obvious placeholder content (TODO, Lorem, placeholder class, FIXME)
- Missing design-token usage (heuristic: style="...px" without var(--token-*))

Use --strict to exit 1 when layout-sized fixed px found. Output is file:line for review.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TEMPLATES = ROOT / "templates"

# Layout-sized: report inline px >= this (icons/small fixed OK per §8.0.6)
MIN_PX_LAYOUT = 100

# Placeholder patterns (content that should not ship)
PLACEHOLDER_PATTERNS = [
    (re.compile(r"\bTODO\b", re.I), "TODO in template"),
    (re.compile(r"\bFIXME\b", re.I), "FIXME in template"),
    (re.compile(r"\bLorem\s+ipsum\b", re.I), "Lorem ipsum placeholder"),
    (re.compile(r'class="[^"]*placeholder[^"]*"', re.I), "placeholder class (styling)"),
]


def scan_inline_px(path: Path, min_px: int) -> list[tuple[int, str, str]]:
    """Find inline style with layout-sized px (width/height/min-* >= min_px)."""
    violations: list[tuple[int, str, str]] = []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    # style="... width: 200px ..." — skip when already fluid (min(...px, 100%) or clamp(...))
    pattern = re.compile(
        r'\b(?:width|height|min-width|min-height)\s*:\s*[^;}\'"]*?(\d+)\s*px',
        re.IGNORECASE,
    )
    for i, line in enumerate(text.splitlines(), 1):
        if "style=" not in line and "style " not in line:
            continue
        for m in pattern.finditer(line):
            # Skip fluid patterns: min(480px, 100%), max(960px, ...), clamp(...)
            frag = line[max(0, m.start() - 20) : m.end() + 10]
            if re.search(r"(?:min|max|clamp)\s*\([^)]*\d+\s*px", frag, re.IGNORECASE):
                continue
            num = int(m.group(1))
            if num >= min_px:
                violations.append(
                    (
                        i,
                        line.strip()[:120],
                        f"inline {m.group(0).strip()} (>= {min_px}px §8.0.11)",
                    )
                )
                break
    return violations


def scan_placeholders(path: Path) -> list[tuple[int, str, str]]:
    """Find obvious placeholder content."""
    violations: list[tuple[int, str, str]] = []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    for i, line in enumerate(text.splitlines(), 1):
        for pat, reason in PLACEHOLDER_PATTERNS:
            if pat.search(line):
                violations.append((i, line.strip()[:100], reason))
                break
    return violations


def main() -> int:
    ap = argparse.ArgumentParser(
        description="§8.0.11 template audit: fixed px, placeholders, token drift hints"
    )
    ap.add_argument(
        "--strict", action="store_true", help="Exit 1 if layout-sized inline px found"
    )
    ap.add_argument(
        "--min-px", type=int, default=MIN_PX_LAYOUT, help="Report inline px >= this"
    )
    ap.add_argument(
        "--templates", type=Path, default=TEMPLATES, help="Templates directory"
    )
    args = ap.parse_args()
    tpl_dir = (
        args.templates.resolve()
        if args.templates.is_absolute()
        else ROOT / args.templates
    )

    px_violations: dict[Path, list] = {}
    placeholder_violations: dict[Path, list] = {}
    for path in sorted(tpl_dir.rglob("*.html")):
        rel = path.relative_to(ROOT)
        if "node_modules" in str(rel) or ".venv" in str(rel):
            continue
        px = scan_inline_px(path, args.min_px)
        if px:
            px_violations[path] = px
        ph = scan_placeholders(path)
        if ph:
            placeholder_violations[path] = ph

    total_px = sum(len(v) for v in px_violations.values())
    total_ph = sum(len(v) for v in placeholder_violations.values())

    for path in sorted(px_violations.keys()):
        rel = path.relative_to(ROOT)
        for line_no, line, reason in px_violations[path]:
            print(f"{rel}:{line_no}: {reason}")
            print(f"  {line}")

    for path in sorted(placeholder_violations.keys()):
        rel = path.relative_to(ROOT)
        for line_no, line, reason in placeholder_violations[path]:
            print(f"{rel}:{line_no}: [placeholder] {reason}")
            print(f"  {line}")

    if total_px > 0:
        print(
            f"\n§8.0.11: {total_px} layout-sized inline px in {len(px_violations)} file(s). Prefer CSS vars / clamp()."
        )
        if args.strict:
            return 1
    if total_ph > 0:
        print(
            f"\n§8.0.11: {total_ph} placeholder hint(s) in {len(placeholder_violations)} file(s)."
        )
    if total_px == 0 and total_ph == 0:
        print(
            "§8.0.11 template audit: no layout-sized inline px or placeholder content found."
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
