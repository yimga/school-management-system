"""One-off repair for _pages JS files where the page-data-island converter
emitted a JS property-read expression inside the surrounding string-literal
quotes — turning a real expression into a literal string that just happens
to spell out the expression.

Pattern emitted by the broken converter:
    "(window.__RMC_PAGE_DATA__["slug"]||{})["key"]"

Correct shape (real property read):
    ((window.__RMC_PAGE_DATA__["slug"]||{})["key"])

This script scans static/js/_pages/*.js, finds those wrapped-in-quotes
expressions in BOTH double-quoted and single-quoted string contexts, and
unwraps them. Reports every change. Dry-run by default.

Idempotent: re-running on an already-fixed file is a no-op.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAGES_DIR = ROOT / "static" / "js" / "_pages"

# Match a string literal whose body is *exactly* a page-data property read:
#   "(window.__RMC_PAGE_DATA__["..."]||{})["..."]"
# or the equivalent with the outer string in single quotes.
# We deliberately use a permissive inner [^"]/[^'] match because the
# emitted expressions contain their own (different-quote) JSON keys.
PATTERNS = [
    # Outer double quotes wrapping a `(window.__RMC_PAGE_DATA__["..."]||{})["..."]`
    re.compile(
        r'"\(window\.__RMC_PAGE_DATA__\[\"([^\"]+)\"\]\|\|\{\}\)\[\"([^\"]+)\"\]"'
    ),
    # Outer single quotes wrapping the same expression — the inner JSON keys
    # are still double-quoted because the converter always emitted them that way.
    re.compile(
        r"'\(window\.__RMC_PAGE_DATA__\[\"([^\"]+)\"\]\|\|\{\}\)\[\"([^\"]+)\"\]'"
    ),
]

REPLACEMENT_TEMPLATE = '((window.__RMC_PAGE_DATA__["{slug}"] || {{}})["{key}"])'


def _unwrap(text: str) -> tuple[str, int]:
    count = 0

    def _sub(m: re.Match) -> str:
        nonlocal count
        count += 1
        slug, key = m.group(1), m.group(2)
        return REPLACEMENT_TEMPLATE.format(slug=slug, key=key)

    for pat in PATTERNS:
        text, n = pat.subn(_sub, text)
        # `subn` already updated count via _sub — n is the same total; do not
        # double-count.
    return text, count


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="write changes (default: dry-run)")
    ap.add_argument(
        "--file",
        action="append",
        default=[],
        help="restrict to specific filenames (basename only); may repeat",
    )
    args = ap.parse_args()

    if not PAGES_DIR.is_dir():
        print(f"!! pages dir not found: {PAGES_DIR}", file=sys.stderr)
        return 2

    files = sorted(PAGES_DIR.glob("*.js"))
    if args.file:
        wanted = set(args.file)
        files = [f for f in files if f.name in wanted]

    touched = 0
    total = 0
    for path in files:
        src = path.read_text(encoding="utf-8", errors="replace")
        new, n = _unwrap(src)
        if n == 0:
            continue
        total += n
        touched += 1
        action = "would-fix" if not args.apply else "fixed"
        print(f"[{action}] {path.relative_to(ROOT)} — {n} occurrence(s)")
        if args.apply:
            path.write_text(new, encoding="utf-8", newline="\n")

    print(f"\n{touched} file(s), {total} occurrence(s) {'fixed' if args.apply else 'would be fixed'}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
