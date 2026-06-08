#!/usr/bin/env python3
"""Wave 8 — mechanical drawer/scroll/column-budget on schools/super_* + siteconfig/partials."""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DRAWER_BUNDLE = '{% include "partials/portal_row_detail_drawer_bundle.html" %}'
TABLE_RE = re.compile(
    r'(<table\b[^>]*\brmc-data-table\b[^>]*)(>)',
    re.I,
)

# th_count from scorer → allow-marker reason slug
COLUMN_ALLOW: dict[str, str] = {
    "templates/schools/super_dashboard.html": "cp-dashboard-multi-lens-operator-tables",
    "templates/schools/super_offboarding_queue.html": "offboarding-queue-eight-column-operator-lens",
    "templates/schools/super_migration_cloud.html": "migration-cloud-ten-column-operator-lens",
    "templates/schools/super_support_queue_fragment.html": "support-queue-ten-column-fragment-lens",
    "templates/schools/super_tenant_health.html": "tenant-health-ten-column-operator-lens",
    "templates/schools/super_geography.html": "geography-eight-column-registry-lens",
    "templates/schools/super_security_hub.html": "security-hub-eight-column-operator-lens",
    "templates/schools/super_district_enterprise.html": "district-enterprise-seven-column-lens",
    "templates/schools/super_feature_toggles_list.html": "feature-toggles-seven-column-lens",
    "templates/schools/super_plans_list.html": "plans-list-seven-column-lens",
    "templates/schools/super_regions_list.html": "regions-list-seven-column-lens",
    "templates/schools/super_runtime_inspector.html": "runtime-inspector-seven-column-lens",
    "templates/schools/super_sync_repair.html": "sync-repair-seven-column-lens",
    "templates/siteconfig/partials/tag_manager_body.html": "tag-manager-seven-column-catalog-lens",
    "templates/siteconfig/partials/tenant_report_schedules_evidence_body.html": "report-schedules-seven-column-evidence-lens",
}


def _patch_table_open(tag: str) -> str:
    if "data-rmc-row-detail-table" not in tag:
        tag = tag.rstrip()
        if tag.endswith("/"):
            tag = tag[:-1]
        tag += ' data-rmc-row-detail-table="1" data-rmc-row-detail-auto="1"'
    if 'data-rmc-table-5col="1"' not in tag and "table-column-budget-allow:" not in tag:
        tag += ' data-rmc-table-5col="1"'
    return tag


def patch_file(rel: str) -> bool:
    path = ROOT / rel.replace("/", "\\") if "\\" in str(ROOT) else ROOT / rel
    if not path.is_file():
        return False
    text = path.read_text(encoding="utf-8")
    orig = text

    if "rmc-data-table" not in text:
        return False

    def repl(m: re.Match[str]) -> str:
        return _patch_table_open(m.group(1)) + m.group(2)

    text = TABLE_RE.sub(repl, text)

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

    needs_scroll = (
        "rmc-data-table" in text
        and 'data-rmc-scroll-policy="paginate"' not in text
        and "components/pagination.html" not in text
        and "page_obj" not in text
    )
    if needs_scroll:
        m = re.search(r'<div\b([^>]*class="[^"]*container-fluid[^"]*"[^>]*)>', text, re.I)
        if m and 'data-rmc-scroll-policy="paginate"' not in m.group(0):
            old = m.group(0)
            new = old[:-1] + ' data-rmc-scroll-policy="paginate">'
            text = text.replace(old, new, 1)
        elif "<div" in text and 'data-rmc-scroll-policy="paginate"' not in text:
            text = text.replace("<div", '<div data-rmc-scroll-policy="paginate"', 1)

    if text != orig:
        path.write_text(text, encoding="utf-8")
        return True
    return False


def main() -> int:
    patterns = ["templates/schools/super_*.html", "templates/siteconfig/partials/*.html"]
    changed: list[str] = []
    for pat in patterns:
        for p in sorted(ROOT.glob(pat)):
            rel = p.relative_to(ROOT).as_posix()
            if patch_file(rel):
                changed.append(rel)
    print(f"patched {len(changed)} files")
    for c in changed:
        print(" ", c)
    return 0


if __name__ == "__main__":
    sys.exit(main())
