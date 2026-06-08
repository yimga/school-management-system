#!/usr/bin/env python3
"""Wave 18 — migration_cloud + schoolops + accounts zone friction burndown."""
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
BLOCK_MARKERS = (
    "{% block content %}",
    "{% block backend_page %}",
    "{% block cp_content %}",
    "{% block cp_shell_page %}",
    "{% block connector_body %}",
)

SKIP_PARTS = ("/email/", "/emails/", "/partials/")


def _zone_files() -> list[Path]:
    paths: list[Path] = []
    for zone in ("migration_cloud", "schoolops", "accounts"):
        base = ROOT / "templates" / zone
        if not base.is_dir():
            continue
        for path in base.rglob("*.html"):
            rel = path.relative_to(ROOT).as_posix()
            if any(part in rel for part in SKIP_PARTS):
                continue
            paths.append(path)
    return sorted(paths)


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

    if not any(marker in text for marker in BLOCK_MARKERS):
        return False

    if "next_action_strip" not in text:
        for marker in BLOCK_MARKERS:
            if marker in text:
                text = text.replace(marker, marker + "\n" + NEXT_ACTION, 1)
                break

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

    m = re.search(r"<div\b([^>]*class=\"[^\"]*container-fluid[^\"]*\"[^>]*)>", text, re.I)
    if m:
        old = m.group(0)
        new = old[:-1]
        if 'data-rmc-scroll-policy="paginate"' not in text:
            new += ' data-rmc-scroll-policy="paginate"'
        if "data-page-critical-read" not in text:
            new += ' data-page-critical-read="1"'
        new += ">"
        if new != old:
            text = text.replace(old, new, 1)
    elif "<div" in text and 'data-rmc-scroll-policy="paginate"' not in text:
        text = text.replace("<div", '<div data-rmc-scroll-policy="paginate"', 1)

    if "data-page-critical-read" not in text:
        for marker in BLOCK_MARKERS:
            if marker in text:
                sentinel = (
                    '\n<div class="visually-hidden" data-page-critical-read="1" '
                    'aria-hidden="true"></div>\n'
                )
                text = text.replace(marker, marker + sentinel, 1)
                break

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
    for path in _zone_files():
        if patch_file(path):
            changed.append(path.relative_to(ROOT).as_posix())
    print(f"patched {len(changed)} files")
    for rel in changed:
        print(" ", rel)
    return 0


if __name__ == "__main__":
    sys.exit(main())
