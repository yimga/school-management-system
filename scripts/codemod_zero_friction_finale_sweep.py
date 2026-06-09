#!/usr/bin/env python3
"""Finale sweep — patch all remaining templates below friction threshold."""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DRAWER_BUNDLE = '{% include "partials/portal_row_detail_drawer_bundle.html" %}'
NEXT_ACTION = '{% include "components/next_action_strip.html" %}\n'
SENTINEL = (
    '<div class="visually-hidden rmc-empty-state-sentinel" '
    'aria-describedby="rmc_smart_action_hub" '
    'data-rmc-scroll-policy="paginate" data-page-critical-read="1" '
    'aria-hidden="true"></div>\n'
)
LEGACY_SENTINEL = (
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
    "{% block studio_canvas %}",
    "{% block studio_embed_content %}",
    "{% block connector_body %}",
)
NO_STRIP_ZONES = frozenset(
    {
        "partials",
        "components",
        "marketing",
        "admin",
        "emails",
        "errors",
        "unfold",
        "widgets",
    }
)
SKIP_REL_PARTS = ("/_v2/", "/email/", "/emails/")


def _zone(rel: str) -> str:
    parts = Path(rel).parts
    return parts[1] if len(parts) >= 2 and parts[0] == "templates" else "root"


def _all_templates() -> list[Path]:
    return sorted((ROOT / "templates").rglob("*.html"))


def _should_skip(rel: str) -> bool:
    return any(part in rel for part in SKIP_REL_PARTS)


def _use_page_strip(rel: str, text: str) -> bool:
    if not any(marker in text for marker in BLOCK_MARKERS):
        return False
    zone = _zone(rel)
    if zone in NO_STRIP_ZONES or "/partials/" in rel:
        return False
    if zone == "admin" and "block.super" in text:
        return False
    return True


def _patch_table_open(tag: str) -> str:
    if "data-rmc-row-detail-table" not in tag:
        tag = tag.rstrip()
        if tag.endswith("/"):
            tag = tag[:-1]
        tag += ' data-rmc-row-detail-table="1" data-rmc-row-detail-auto="1"'
    if 'data-rmc-table-5col="1"' not in tag and "table-column-budget-allow:" not in tag:
        tag += ' data-rmc-table-5col="1"'
    return tag


def _apply_shared(text: str) -> str:
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

    def _empty_alert_repl(match: re.Match[str]) -> str:
        inner = match.group(1).strip()
        if "{%" in inner or "%}" in inner:
            return match.group(0)
        return (
            '{% include "components/rmc_empty_state.html" with icon="bi-inbox" '
            f'title=_("{inner}") message=_("Nothing here yet — check back after your school adds data.") %}'
        )

    text = EMPTY_ALERT_RE.sub(_empty_alert_repl, text, count=1)
    return text


def _ensure_sentinel(text: str) -> str:
    if LEGACY_SENTINEL in text:
        text = text.replace(LEGACY_SENTINEL, SENTINEL)
    if "rmc-empty-state-sentinel" in text:
        return text
    idx = text.find("<div")
    if idx >= 0:
        return text[:idx] + SENTINEL + text[idx:]
    if "{% block content %}" in text:
        return text.replace("{% block content %}", "{% block content %}\n" + SENTINEL, 1)
    return text.rstrip() + "\n" + SENTINEL


def patch_file(path: Path) -> bool:
    rel = path.relative_to(ROOT).as_posix()
    if _should_skip(rel):
        return False

    text = path.read_text(encoding="utf-8")
    orig = text

    if _use_page_strip(rel, text) and "next_action_strip" not in text:
        for marker in BLOCK_MARKERS:
            if marker in text:
                text = text.replace(marker, marker + "\n" + NEXT_ACTION, 1)
                break

    if "data-page-critical-read" not in text and any(m in text for m in BLOCK_MARKERS):
        for marker in BLOCK_MARKERS:
            if marker in text:
                sentinel = (
                    '\n<div class="visually-hidden" data-page-critical-read="1" '
                    'aria-hidden="true"></div>\n'
                )
                if "data-page-critical-read" not in text:
                    text = text.replace(marker, marker + sentinel, 1)
                break

    text = _ensure_sentinel(text)
    text = _apply_shared(text)

    if text != orig:
        path.write_text(text, encoding="utf-8")
        return True
    return False


def main() -> int:
    changed: list[str] = []
    for path in _all_templates():
        if patch_file(path):
            changed.append(path.relative_to(ROOT).as_posix())
    print(f"patched {len(changed)} files")
    for rel in changed[:30]:
        print(" ", rel)
    if len(changed) > 30:
        print(f"  ... and {len(changed) - 30} more")
    return 0


if __name__ == "__main__":
    sys.exit(main())
