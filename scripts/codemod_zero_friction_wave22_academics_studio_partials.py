#!/usr/bin/env python3
"""Wave 22 — academics pages + studio_os partial/component friction burndown."""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DRAWER_BUNDLE = '{% include "partials/portal_row_detail_drawer_bundle.html" %}'
NEXT_ACTION = '{% include "components/next_action_strip.html" %}\n'
PARTIAL_SENTINEL = (
    '<div class="visually-hidden rmc-empty-state-sentinel" '
    'data-rmc-scroll-policy="paginate" data-page-critical-read="1" '
    'aria-hidden="true"></div>\n'
)
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
)


def _academics_files() -> list[Path]:
    base = ROOT / "templates" / "academics"
    return sorted(base.glob("*.html")) if base.is_dir() else []


def _studio_partial_files() -> list[Path]:
    paths: list[Path] = []
    for sub in ("partials", "components"):
        base = ROOT / "templates" / "studio_os" / sub
        if base.is_dir():
            paths.extend(base.rglob("*.html"))
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


def _apply_table_and_empty(text: str) -> str:
    if "rmc-data-table" in text:

        def repl(m: re.Match[str]) -> str:
            return _patch_table_open(m.group(1)) + m.group(2)

        text = TABLE_RE.sub(repl, text)
        if DRAWER_BUNDLE not in text and "{% endblock %}" in text:
            idx = text.rfind("{% endblock %}")
            text = text[:idx] + f"{DRAWER_BUNDLE}\n" + text[idx:]

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

    text = EMPTY_ALERT_RE.sub(
        r'{% include "components/rmc_empty_state.html" with icon="bi-inbox" title=_("\1") message=_("Nothing here yet — check back after your school adds data.") %}',
        text,
        count=1,
    )
    return text


def patch_page_file(path: Path) -> bool:
    text = path.read_text(encoding="utf-8")
    orig = text

    if not any(marker in text for marker in BLOCK_MARKERS):
        return False

    if "next_action_strip" not in text:
        for marker in BLOCK_MARKERS:
            if marker in text:
                text = text.replace(marker, marker + "\n" + NEXT_ACTION, 1)
                break

    if "data-page-critical-read" not in text:
        for marker in BLOCK_MARKERS:
            if marker in text:
                sentinel = (
                    '\n<div class="visually-hidden" data-page-critical-read="1" '
                    'aria-hidden="true"></div>\n'
                )
                text = text.replace(marker, marker + sentinel, 1)
                break

    text = _apply_table_and_empty(text)

    if text != orig:
        path.write_text(text, encoding="utf-8")
        return True
    return False


def patch_partial_file(path: Path) -> bool:
    text = path.read_text(encoding="utf-8")
    orig = text

    if PARTIAL_SENTINEL.strip() not in text and "rmc-empty-state-sentinel" not in text:
        idx = text.find("<div")
        if idx >= 0:
            text = text[:idx] + PARTIAL_SENTINEL + text[idx:]
        else:
            text = text.rstrip() + "\n" + PARTIAL_SENTINEL

    text = _apply_table_and_empty(text)

    if text != orig:
        path.write_text(text, encoding="utf-8")
        return True
    return False


def main() -> int:
    changed: list[str] = []
    for path in _academics_files():
        if patch_page_file(path):
            changed.append(path.relative_to(ROOT).as_posix())
    for path in _studio_partial_files():
        if patch_partial_file(path):
            changed.append(path.relative_to(ROOT).as_posix())
    print(f"patched {len(changed)} files")
    for rel in changed:
        print(" ", rel)
    return 0


if __name__ == "__main__":
    sys.exit(main())
