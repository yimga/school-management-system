#!/usr/bin/env python3
"""Wave 12 — drawer/scroll/column-budget on migration_cloud + siteconfig metadata."""
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
DL_RE = re.compile(
    r"(<dl\b[^>]*\brmc-data-table\b[^>]*)(>)",
    re.I,
)

COLUMN_ALLOW: dict[str, str] = {
    "templates/migration_cloud/console.html": "migration-cloud-console-eight-column-lens",
    "templates/migration_cloud/operator/audit_dashboard.html": "migration-audit-dashboard-eight-column-lens",
    "templates/migration_cloud/operator/dlq_list.html": "migration-dlq-ten-column-operator-lens",
    "templates/migration_cloud/operator/smoke_history.html": "migration-smoke-history-seven-column-lens",
    "templates/migration_cloud/operator/token_list.html": "migration-token-list-eight-column-lens",
    "templates/migration_cloud/operator/token_rotation_chain.html": "migration-token-rotation-ten-column-lens",
    "templates/migration_cloud/operator/webhook_audit.html": "migration-webhook-audit-eleven-column-lens",
    "templates/migration_cloud/operator/webhook_delivery_log.html": "migration-webhook-delivery-ten-column-lens",
    "templates/migration_cloud/operator/webhook_list.html": "migration-webhook-list-nine-column-lens",
    "templates/migration_cloud/super/vendor_write_status.html": "migration-vendor-write-seven-column-lens",
    "templates/siteconfig/entity_catalog_overview.html": "entity-catalog-seven-column-operator-lens",
    "templates/siteconfig/grading_scale_bands.html": "grading-scale-bands-eight-column-lens",
    "templates/siteconfig/installed_packages_rollback.html": "installed-packages-nine-column-rollback-lens",
    "templates/siteconfig/metadata_dynamic_fields_operator.html": "metadata-dynamic-fields-six-column-lens",
}


def _patch_rmc_surface(tag: str) -> str:
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
        r'<section\b([^>]*)>',
        r'<main\b([^>]*)>',
    ):
        m = re.search(pattern, text, re.I)
        if m and 'data-rmc-scroll-policy="paginate"' not in m.group(0):
            old = m.group(0)
            return text.replace(old, old[:-1] + ' data-rmc-scroll-policy="paginate">', 1)
    if "{% block content %}" in text or "{% block cp_content %}" in text:
        for block in ("{% block cp_content %}", "{% block content %}"):
            if block in text:
                opened = text.replace(
                    block,
                    block + '\n<div data-rmc-scroll-policy="paginate">',
                    1,
                )
                idx = opened.rfind("{% endblock %}")
                if idx != -1:
                    return opened[:idx] + "</div>\n" + opened[idx:]
                return opened
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

    text = TABLE_RE.sub(lambda m: _patch_rmc_surface(m.group(1)) + m.group(2), text)
    text = DL_RE.sub(lambda m: _patch_rmc_surface(m.group(1)) + m.group(2), text)

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

    text = _inject_scroll_policy(text)

    if text != orig:
        path.write_text(text, encoding="utf-8")
        return True
    return False


def main() -> int:
    changed: list[str] = []
    for p in sorted((ROOT / "templates/migration_cloud").rglob("*.html")):
        rel = p.relative_to(ROOT).as_posix()
        if patch_file(rel):
            changed.append(rel)
    for p in sorted((ROOT / "templates/siteconfig").glob("*.html")):
        rel = p.relative_to(ROOT).as_posix()
        if patch_file(rel):
            changed.append(rel)
    print(f"patched {len(changed)} files")
    for c in changed:
        print(" ", c)
    return 0


if __name__ == "__main__":
    sys.exit(main())
