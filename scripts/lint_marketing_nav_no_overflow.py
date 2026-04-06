#!/usr/bin/env python3
"""
Lint: marketing nav must not overflow (no horizontal scroll).
Checks that either (1) primary nav items <= 7, or (2) template/context uses
overflow handling (e.g. More dropdown + marketing_navbar_has_more).

Run: ``raise SystemExit(main(None))`` (default ``--base`` is this repository root).

Exit 0 if OK; 1 if nav would overflow without handling.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MAX_TOP_LEVEL = 7


def _resolve_base(base: str) -> Path:
    root = Path(base).resolve()
    if not root.is_dir():
        raise ValueError(f"--base path does not exist or is not a directory: {base}")
    return root


def count_primary_items(root: Path) -> int:
    views = root / "apps" / "schools" / "marketing_views.py"
    text = views.read_text(encoding="utf-8")
    # Find _marketing_navbar_primary return list: count {"label": ...} entries
    start = text.find("def _marketing_navbar_primary()")
    if start == -1:
        return 0
    block = text[start : start + 4000]
    # Count lines like {"label": "Product", "path": ...}
    return len(re.findall(r'\{"label"\s*:', block))


def has_overflow_handling(root: Path) -> bool:
    # Template has More dropdown and uses marketing_navbar_has_more or visible_count / forloop split
    header_tpl = root / "templates" / "marketing" / "marketing_header.html"
    if not header_tpl.exists():
        return False
    text = header_tpl.read_text(encoding="utf-8")
    has_more = "marketing_navbar_has_more" in text or "More" in text
    has_overflow_split = (
        "marketing_navbar_visible_count" in text
        or "forloop.counter > 7" in text
        or "forloop.counter <= 7" in text
    )
    return bool(has_more and has_overflow_split)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Lint marketing nav overflow handling."
    )
    parser.add_argument(
        "--base",
        default=str(ROOT),
        help="Repository root (defaults to this repository root).",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        root = _resolve_base(args.base)
    except ValueError as exc:
        print(f"lint_marketing_nav_no_overflow: {exc}", file=sys.stderr)
        return 1

    n = count_primary_items(root)
    if n <= MAX_TOP_LEVEL:
        print(
            f"[lint_marketing_nav_no_overflow] OK: {n} primary items (<= {MAX_TOP_LEVEL})"
        )
        return 0
    if has_overflow_handling(root):
        print(
            f"[lint_marketing_nav_no_overflow] OK: {n} items but overflow handled (More dropdown)"
        )
        return 0
    print(
        f"[lint_marketing_nav_no_overflow] FAIL: {n} primary items > {MAX_TOP_LEVEL} and no overflow handling",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main(None))
