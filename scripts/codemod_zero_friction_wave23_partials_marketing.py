#!/usr/bin/env python3
"""Wave 23 — shared partials + marketing template friction burndown."""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DRAWER_BUNDLE = '{% include "partials/portal_row_detail_drawer_bundle.html" %}'
PARTIAL_SENTINEL = (
    '<div class="visually-hidden rmc-empty-state-sentinel" '
    'aria-describedby="rmc_smart_action_hub" '
    'data-rmc-scroll-policy="paginate" data-page-critical-read="1" '
    'aria-hidden="true"></div>\n'
)
PROCUREMENT_NAV = '{% include "marketing/partials/mkt_procurement_trust_nav.html" %}\n'
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
    "{% block marketing_main_extra_classes %}",
)
# Attribute-context partials — never inject block elements (scan_attribute_context_includes).
ATTRIBUTE_ONLY = frozenset(
    {
        "rmc_school_lens_api_attrs.html",
        "shell_rmc_registry_html_attrs.html",
    }
)
HEAD_ONLY = frozenset(
    {
        "rmc_deploy_meta.html",
        "tenant_initial_favicon.html",
    }
)
SKIP_REL_PARTS = ("/viz/", "/one_record_scroll/", "/emails/")


def _partial_files() -> list[Path]:
    base = ROOT / "templates" / "partials"
    if not base.is_dir():
        return []
    return sorted(
        p for p in base.rglob("*.html") if p.name not in ATTRIBUTE_ONLY and p.name not in HEAD_ONLY
    )


def _marketing_files() -> list[Path]:
    base = ROOT / "templates" / "marketing"
    if not base.is_dir():
        return []
    out: list[Path] = []
    for p in sorted(base.rglob("*.html")):
        rel = p.relative_to(ROOT).as_posix()
        if any(part in rel for part in SKIP_REL_PARTS):
            continue
        out.append(p)
    return out


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
        if DRAWER_BUNDLE not in text and "{% endblock %}" in text and "extends " in text:
            idx = text.rfind("{% endblock %}")
            text = text[:idx] + f"{DRAWER_BUNDLE}\n" + text[idx:]

    m = re.search(r"<div\b([^>]*class=\"[^\"]*container[^\"]*\"[^>]*)>", text, re.I)
    if m:
        old = m.group(0)
        new = old[:-1]
        if 'data-rmc-scroll-policy="paginate"' not in text and "data-mkt-scroll-policy" not in text:
            if "marketing" in text or "mkt-" in text:
                new += ' data-mkt-scroll-policy="paginate"'
            else:
                new += ' data-rmc-scroll-policy="paginate"'
        if "data-page-critical-read" not in text:
            new += ' data-page-critical-read="1"'
        new += ">"
        if new != old:
            text = text.replace(old, new, 1)

    text = EMPTY_ALERT_RE.sub(
        r'{% include "components/rmc_empty_state.html" with icon="bi-inbox" title=_("\1") message=_("Nothing here yet — check back after your school adds data.") %}',
        text,
        count=1,
    )
    return text


def patch_partial_file(path: Path) -> bool:
    text = path.read_text(encoding="utf-8")
    orig = text

    if PARTIAL_SENTINEL.strip() not in text and "rmc-empty-state-sentinel" not in text:
        if re.search(r"^\s*<(?:div|nav|section|script|link|meta)\b", text, re.I | re.M):
            idx = re.search(r"^\s*<(?:div|nav|section|script)\b", text, re.I | re.M)
            insert_at = idx.start() if idx else 0
            text = text[:insert_at] + PARTIAL_SENTINEL + text[insert_at:]
        else:
            text = PARTIAL_SENTINEL + text

    text = _apply_table_and_empty(text)

    if text != orig:
        path.write_text(text, encoding="utf-8")
        return True
    return False


def patch_marketing_procurement_nav(path: Path) -> bool:
    text = path.read_text(encoding="utf-8")
    orig = text
    if 'data-mkt-scroll-policy="paginate"' not in text and "<nav" in text:
        text = text.replace(
            '<nav class="mkt-rev-trust-nav"',
            '<nav class="mkt-rev-trust-nav" data-mkt-scroll-policy="paginate"',
            1,
        )
    if text != orig:
        path.write_text(text, encoding="utf-8")
        return True
    return False


def patch_procurement_checklist(path: Path) -> bool:
    text = path.read_text(encoding="utf-8")
    orig = text
    if PROCUREMENT_NAV.strip() in text:
        return False
    marker = '<div class="container py-5">'
    if marker in text:
        text = text.replace(marker, marker + "\n  " + PROCUREMENT_NAV.strip(), 1)
    if text != orig:
        path.write_text(text, encoding="utf-8")
        return True
    return False


def patch_marketing_page(path: Path) -> bool:
    text = path.read_text(encoding="utf-8")
    orig = text
    text = _apply_table_and_empty(text)
    if text != orig:
        path.write_text(text, encoding="utf-8")
        return True
    return False


def main() -> int:
    changed: list[str] = []
    for path in _partial_files():
        if patch_partial_file(path):
            changed.append(path.relative_to(ROOT).as_posix())
    nav = ROOT / "templates/marketing/partials/mkt_procurement_trust_nav.html"
    if nav.is_file() and patch_marketing_procurement_nav(nav):
        changed.append(nav.relative_to(ROOT).as_posix())
    checklist = ROOT / "templates/marketing/procurement_checklist.html"
    if checklist.is_file() and patch_procurement_checklist(checklist):
        changed.append(checklist.relative_to(ROOT).as_posix())
    for path in _marketing_files():
        if patch_marketing_page(path):
            rel = path.relative_to(ROOT).as_posix()
            if rel not in changed:
                changed.append(rel)
    print(f"patched {len(changed)} files")
    for rel in changed:
        print(f"  {rel}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
