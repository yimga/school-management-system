#!/usr/bin/env python3
"""
Lint: marketing nav must not overflow (no horizontal scroll).
Checks that either (1) primary nav items <= 7, or (2) template/context uses
overflow handling (e.g. More dropdown + marketing_navbar_has_more).
Exit 0 if OK; 1 if nav would overflow without handling.
"""

from pathlib import Path
import re
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
VIEWS = REPO_ROOT / "apps" / "schools" / "marketing_views.py"
HEADER_TPL = REPO_ROOT / "templates" / "marketing" / "marketing_header.html"
MAX_TOP_LEVEL = 7


def count_primary_items() -> int:
    text = VIEWS.read_text(encoding="utf-8")
    # Find _marketing_navbar_primary return list: count {"label": ...} entries
    start = text.find("def _marketing_navbar_primary()")
    if start == -1:
        return 0
    block = text[start : start + 4000]
    # Count lines like {"label": "Product", "path": ...}
    return len(re.findall(r'\{"label"\s*:', block))


def has_overflow_handling() -> bool:
    # Template has More dropdown and uses marketing_navbar_has_more or visible_count / forloop split
    if not HEADER_TPL.exists():
        return False
    text = HEADER_TPL.read_text(encoding="utf-8")
    has_more = "marketing_navbar_has_more" in text or "More" in text
    has_overflow_split = (
        "marketing_navbar_visible_count" in text
        or "forloop.counter > 7" in text
        or "forloop.counter <= 7" in text
    )
    return bool(has_more and has_overflow_split)


def main() -> int:
    n = count_primary_items()
    if n <= MAX_TOP_LEVEL:
        print(
            f"[lint_marketing_nav_no_overflow] OK: {n} primary items (<= {MAX_TOP_LEVEL})"
        )
        return 0
    if has_overflow_handling():
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
    sys.exit(main())
