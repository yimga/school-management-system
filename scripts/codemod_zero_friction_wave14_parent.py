#!/usr/bin/env python3
"""Wave 14 — parent zone friction burndown (next-action strip, 5-col, drawer, empty states)."""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DRAWER_BUNDLE = '{% include "partials/portal_row_detail_drawer_bundle.html" %}'
NEXT_ACTION = '{% include "components/next_action_strip.html" %}\n'
TABLE_RE = re.compile(
    r"(<table\b[^>]*\brmc-data-table\b[^>]*)(>)",
    re.I,
)
EMPTY_ALERT_RE = re.compile(
    r'<div class="alert alert-info(?: mb-0)?">([^<]+)</div>',
    re.I,
)

PARENT_FILES = sorted((ROOT / "templates" / "parent").glob("*.html"))


def _patch_table_open(tag: str) -> str:
    if "data-rmc-row-detail-table" not in tag:
        tag = tag.rstrip()
        if tag.endswith("/"):
            tag = tag[:-1]
        tag += ' data-rmc-row-detail-table="1" data-rmc-row-detail-auto="1"'
    if 'data-rmc-table-5col="1"' not in tag and "table-column-budget-allow:" not in tag:
        tag += ' data-rmc-table-5col="1"'
    return tag


def patch_file(path: Path) -> bool:
    text = path.read_text(encoding="utf-8")
    orig = text

    if "next_action_strip" not in text:
        marker = "{% block content %}"
        if marker in text:
            text = text.replace(marker, marker + "\n" + NEXT_ACTION, 1)

    if "rmc-data-table" in text:

        def repl(m: re.Match[str]) -> str:
            return _patch_table_open(m.group(1)) + m.group(2)

        text = TABLE_RE.sub(repl, text)

        if DRAWER_BUNDLE not in text:
            if "{% endblock %}" in text:
                idx = text.rfind("{% endblock %}")
                text = text[:idx] + f"{DRAWER_BUNDLE}\n" + text[idx:]
            else:
                text = text.rstrip() + f"\n{DRAWER_BUNDLE}\n"

    if 'data-rmc-scroll-policy="paginate"' not in text:
        m = re.search(r'<div\b([^>]*class="[^"]*container-fluid[^"]*"[^>]*)>', text, re.I)
        if m and 'data-rmc-scroll-policy="paginate"' not in m.group(0):
            old = m.group(0)
            new = old[:-1] + ' data-rmc-scroll-policy="paginate">'
            text = text.replace(old, new, 1)
        elif "<div" in text and 'data-rmc-scroll-policy="paginate"' not in text:
            text = text.replace("<div", '<div data-rmc-scroll-policy="paginate"', 1)

    text = EMPTY_ALERT_RE.sub(
        r'{% include "components/rmc_empty_state.html" with icon="bi-inbox" title=_("\1") message=_("Nothing here yet — check back after your school adds data.") %}',
        text,
        count=1,
    )

    if text != orig:
        path.write_text(text, encoding="utf-8")
        return True
    return False


def main() -> int:
    changed: list[str] = []
    for path in PARENT_FILES:
        if patch_file(path):
            changed.append(path.relative_to(ROOT).as_posix())
    print(f"patched {len(changed)} files")
    for rel in changed:
        print(" ", rel)
    return 0


if __name__ == "__main__":
    sys.exit(main())
