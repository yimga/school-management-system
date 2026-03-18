#!/usr/bin/env python3
"""
Plan A4 / §15: Fail CI when any Python file in apps/ exceeds max line count (mega-file guardrail).
Usage: python scripts/lint_mega_files.py [--max-lines N] [--exit-zero]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

SKIP_DIRS = {"migrations", "__pycache__", "venv", ".venv", "node_modules"}
DEFAULT_MAX_LINES = 4500  # 2.1 splits done; lower to 3500 once siteconfig/models + marketing_views decomposed


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Fail if any app .py file exceeds max lines."
    )
    ap.add_argument(
        "--max-lines",
        type=int,
        default=DEFAULT_MAX_LINES,
        help=f"Max lines per file (default {DEFAULT_MAX_LINES})",
    )
    ap.add_argument(
        "--exit-zero", action="store_true", help="Always exit 0 (report only)."
    )
    ap.add_argument("--base", default=".", help="Base directory (default: .)")
    args = ap.parse_args()
    base = Path(args.base).resolve()
    if not base.is_dir():
        print(f"Not a directory: {base}", file=sys.stderr)
        return 2

    apps_dir = base / "apps"
    if not apps_dir.is_dir():
        print("No apps/ directory.", file=sys.stderr)
        return 0

    hits: list[tuple[str, int]] = []
    for py in apps_dir.rglob("*.py"):
        if any(part in SKIP_DIRS for part in py.parts):
            continue
        try:
            line_count = sum(1 for _ in py.open(encoding="utf-8", errors="replace"))
        except Exception:
            continue
        if line_count > args.max_lines:
            rel = py.relative_to(base)
            hits.append((str(rel).replace("\\", "/"), line_count))

    if not hits:
        print(f"lint_mega_files: No file in apps/ exceeds {args.max_lines} lines.")
        return 0
    print(f"lint_mega_files: Files exceeding {args.max_lines} lines (plan A4 / §15):\n")
    for path, count in sorted(hits, key=lambda x: -x[1]):
        print(f"  {path}: {count} lines")
    print(
        f"\nTotal: {len(hits)} file(s). Decompose by domain (see NEXT_PHASE_BACKLOG A2/B1)."
    )
    return 0 if args.exit_zero else 1


if __name__ == "__main__":
    sys.exit(main())
