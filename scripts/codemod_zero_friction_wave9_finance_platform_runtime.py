#!/usr/bin/env python3
"""Wave 9 — mechanical drawer/scroll/column-budget on finance + platform_runtime templates."""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DRAWER_BUNDLE = '{% include "partials/portal_row_detail_drawer_bundle.html" %}'
TABLE_RE = re.compile(
    r"(<table\b[^>]*\brmc-data-table\b[^>]*)(>)",
    re.I,
)

COLUMN_ALLOW: dict[str, str] = {
    "templates/finance/offline_payment_intent_queue.html": "offline-payment-intent-eight-column-queue-lens",
    "templates/finance/invoices.html": "finance-invoice-ledger-eleven-column-set",
    "templates/platform_runtime/click_measurement_dashboard.html": "click-measurement-seven-column-lens",
    "templates/platform_runtime/configuration_module_detail.html": "configuration-module-seven-column-lens",
    "templates/platform_runtime/registry_health.html": "registry-health-seven-column-lens",
}


def _patch_table_open(tag: str) -> str:
    if "data-rmc-row-detail-table" not in tag:
        tag = tag.rstrip()
        if tag.endswith("/"):
            tag = tag[:-1]
        tag += ' data-rmc-row-detail-table="1" data-rmc-row-detail-auto="1"'
    if 'data-rmc-table-5col="1"' not in tag:
        tag += ' data-rmc-table-5col="1"'
    return tag


def _inject_scroll_policy(text: str) -> str:
    if 'data-rmc-scroll-policy="paginate"' in text:
        return text
    if "components/pagination.html" in text or "page_obj" in text:
        return text
    for pattern in (
        r'<div\b([^>]*class="[^"]*container-fluid[^"]*"[^>]*)>',
        r'<div\b([^>]*class="[^"]*\bcontainer\b[^"]*py-[23][^"]*"[^>]*)>',
        r'<div\b([^>]*class="[^"]*\bcontainer\b[^"]*"[^>]*)>',
    ):
        m = re.search(pattern, text, re.I)
        if m and 'data-rmc-scroll-policy="paginate"' not in m.group(0):
            old = m.group(0)
            return text.replace(old, old[:-1] + ' data-rmc-scroll-policy="paginate">', 1)
    if "<div" in text:
        return text.replace("<div", '<div data-rmc-scroll-policy="paginate"', 1)
    return text


def patch_file(rel: str) -> bool:
    path = ROOT / rel
    if not path.is_file():
        return False
    text = path.read_text(encoding="utf-8")
    orig = text

    if "rmc-data-table" not in text:
        return False

    text = TABLE_RE.sub(lambda m: _patch_table_open(m.group(1)) + m.group(2), text)

    if rel in COLUMN_ALLOW and "table-column-budget-allow:" not in text:
        marker = f"{{# table-column-budget-allow: {COLUMN_ALLOW[rel]} #}}\n"
        if text.startswith("{%"):
            first_nl = text.find("\n")
            text = text[: first_nl + 1] + marker + text[first_nl + 1 :]
        else:
            text = marker + text

    if DRAWER_BUNDLE not in text:
        if "{% endblock %}" in text:
            idx = text.rfind("{% endblock %}")
            text = text[:idx] + f"{DRAWER_BUNDLE}\n" + text[idx:]
        else:
            text = text.rstrip() + f"\n{DRAWER_BUNDLE}\n"

    if "rmc-data-table" in text:
        text = _inject_scroll_policy(text)

    if text != orig:
        path.write_text(text, encoding="utf-8")
        return True
    return False


def main() -> int:
    patterns = [
        "templates/finance/*.html",
        "templates/finance/**/*.html",
        "templates/platform_runtime/*.html",
    ]
    seen: set[str] = set()
    changed: list[str] = []
    for pat in patterns:
        for p in sorted(ROOT.glob(pat)):
            rel = p.relative_to(ROOT).as_posix()
            if rel in seen:
                continue
            seen.add(rel)
            if patch_file(rel):
                changed.append(rel)
    print(f"patched {len(changed)} files")
    for c in changed:
        print(" ", c)
    return 0


if __name__ == "__main__":
    sys.exit(main())
