#!/usr/bin/env python3
"""Gate: operator catalog/list surfaces honor paginate scroll policy (batches 1358/1574–1578)."""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

CATALOG_VIEWS = REPO / "apps/schools/super_views_catalog.py"
FUNNEL_VIEW = REPO / "apps/schools/marketing_views.py"
GROUP_CONSOLE_VIEW = REPO / "apps/schools/views_group_console.py"
METADATA_SERVICES = REPO / "apps/metadata/services.py"

CATALOG_TEMPLATES = (
    "templates/schools/super_workflow_packs.html",
    "templates/schools/super_dashboard_packs.html",
    "templates/schools/super_blueprints_catalog.html",
    "templates/schools/super_policies_catalog.html",
)

WAVE3_TEMPLATES = (
    "templates/schools/super_metadata_catalog.html",
    "templates/schools/group_console.html",
)

WAVE4_VIEWS = (
    ("apps/migration_cloud/views.py", "MigrationCloudConflictsView", "Paginator"),
    (
        "apps/schools/super_views_catalog.py",
        "super_metadata_catalog_field_impact",
        "_paginate_queryset",
    ),
)

WAVE4_TEMPLATES = (
    "templates/migration_cloud/conflicts.html",
    "templates/schools/super_metadata_catalog_field_impact.html",
)

WAVE5_VIEWS = (
    ("apps/marketplace/views.py", "app_catalog", "Paginator"),
    ("apps/marketplace/views.py", "app_catalog", "page_obj"),
    (
        "apps/migration_cloud/views.py",
        "MigrationCloudBundleDetailView",
        "artifacts_page_obj",
    ),
)

WAVE5_TEMPLATES = (
    "templates/marketplace/app_catalog.html",
    "templates/migration_cloud/bundle_detail.html",
)

WAVE5_SERVICES = (
    ("apps/metadata/services.py", "METADATA_CATALOG_FIELD_PREVIEW"),
    ("apps/metadata/services.py", "fields_overflow"),
)


def main() -> int:
    findings: list[str] = []

    views_src = CATALOG_VIEWS.read_text(encoding="utf-8")
    for fn in (
        "super_workflow_packs_catalog",
        "super_dashboard_packs_catalog",
        "super_blueprints_catalog",
        "super_policies_catalog",
    ):
        if fn not in views_src:
            findings.append(f"missing view {fn}")
            continue
        chunk = views_src.split(f"def {fn}", 1)[-1].split("\ndef ", 1)[0]
        if "_paginate_queryset" not in chunk:
            findings.append(f"{fn}: missing _paginate_queryset")
        if '"page_obj"' not in chunk and "'page_obj'" not in chunk:
            findings.append(f"{fn}: missing page_obj in render context")

    if "_CATALOG_PAGE_SIZE = 20" not in views_src:
        findings.append("super_views_catalog.py: expected _CATALOG_PAGE_SIZE = 20")

    for rel in CATALOG_TEMPLATES:
        path = REPO / rel
        if not path.is_file():
            findings.append(f"missing template {rel}")
            continue
        text = path.read_text(encoding="utf-8")
        if 'data-rmc-scroll-policy="paginate"' not in text:
            findings.append(f"{rel}: missing data-rmc-scroll-policy=paginate")
        if "components/pagination.html" not in text:
            findings.append(f"{rel}: missing pagination partial")
        if "page_obj" not in text:
            findings.append(f"{rel}: missing page_obj wiring")

    funnel_src = FUNNEL_VIEW.read_text(encoding="utf-8")
    funnel_chunk = funnel_src.split("def marketing_funnel_dashboard", 1)[-1].split(
        "\ndef ", 1
    )[0]
    if "channel_page_obj" not in funnel_chunk:
        findings.append("marketing_funnel_dashboard: missing channel_page_obj")
    if "Paginator(channel_breakdown" not in funnel_chunk.replace(" ", ""):
        if "Paginator(channel_breakdown" not in funnel_chunk:
            findings.append("marketing_funnel_dashboard: missing Paginator(channel_breakdown")

    funnel_tpl = REPO / "templates/schools/marketing_funnel_dashboard.html"
    if funnel_tpl.is_file():
        ft = funnel_tpl.read_text(encoding="utf-8")
        if "channel_page_obj" not in ft:
            findings.append("marketing_funnel_dashboard.html: missing channel_page_obj")
    else:
        findings.append("missing marketing_funnel_dashboard.html")

    meta_chunk = views_src.split("def super_metadata_catalog", 1)[-1].split("\ndef ", 1)[0]
    if "_paginate_queryset" not in meta_chunk:
        findings.append("super_metadata_catalog: missing _paginate_queryset")
    if "metadata_catalog_queryset" not in meta_chunk:
        findings.append("super_metadata_catalog: missing metadata_catalog_queryset")

    if "def metadata_catalog_queryset" not in METADATA_SERVICES.read_text(encoding="utf-8"):
        findings.append("metadata/services.py: missing metadata_catalog_queryset")

    gc_src = GROUP_CONSOLE_VIEW.read_text(encoding="utf-8")
    gc_chunk = gc_src.split("def group_console", 1)[-1].split("\ndef ", 1)[0]
    if "Paginator" not in gc_chunk or "page_obj" not in gc_chunk:
        findings.append("group_console view: missing Paginator/page_obj")

    for rel in WAVE3_TEMPLATES:
        path = REPO / rel
        if not path.is_file():
            findings.append(f"missing template {rel}")
            continue
        text = path.read_text(encoding="utf-8")
        if "components/pagination.html" not in text:
            findings.append(f"{rel}: missing pagination partial")
        if "page_obj" not in text:
            findings.append(f"{rel}: missing page_obj wiring")

    for rel, fn, needle in WAVE4_VIEWS:
        path = REPO / rel
        if not path.is_file():
            findings.append(f"missing {rel}")
            continue
        src = path.read_text(encoding="utf-8")
        chunk = src.split(f"def {fn}" if fn != "MigrationCloudConflictsView" else f"class {fn}", 1)[
            -1
        ].split("\nclass ", 1)[0].split("\ndef ", 1)[0]
        if needle not in chunk:
            findings.append(f"{fn}: missing {needle}")

    mc_chunk = (REPO / "apps/migration_cloud/views.py").read_text(encoding="utf-8")
    mc_conflicts = mc_chunk.split("class MigrationCloudConflictsView", 1)[-1].split(
        "\nclass ", 1
    )[0]
    if "[:200]" in mc_conflicts or "[:50]" in mc_conflicts:
        findings.append("MigrationCloudConflictsView: hard slice cap still present")

    for rel in WAVE4_TEMPLATES:
        path = REPO / rel
        if not path.is_file():
            findings.append(f"missing template {rel}")
            continue
        text = path.read_text(encoding="utf-8")
        if 'data-rmc-scroll-policy="paginate"' not in text:
            findings.append(f"{rel}: missing data-rmc-scroll-policy=paginate")
        if "page_obj" not in text:
            findings.append(f"{rel}: missing page_obj wiring")

    for rel, fn, needle in WAVE5_VIEWS:
        path = REPO / rel
        if not path.is_file():
            findings.append(f"missing {rel}")
            continue
        src = path.read_text(encoding="utf-8")
        if fn == "MigrationCloudBundleDetailView":
            chunk = src.split(f"class {fn}", 1)[-1].split("\nclass ", 1)[0]
        else:
            chunk = src.split(f"def {fn}", 1)[-1].split("\ndef ", 1)[0]
        if needle not in chunk:
            findings.append(f"{fn}: missing {needle}")

    for rel in WAVE5_TEMPLATES:
        path = REPO / rel
        if not path.is_file():
            findings.append(f"missing template {rel}")
            continue
        text = path.read_text(encoding="utf-8")
        if 'data-rmc-scroll-policy="paginate"' not in text:
            findings.append(f"{rel}: missing data-rmc-scroll-policy=paginate")
        if "components/pagination.html" not in text:
            findings.append(f"{rel}: missing pagination partial")
        if rel.endswith("app_catalog.html"):
            if "page_obj" not in text:
                findings.append(f"{rel}: missing page_obj wiring")
        if rel.endswith("bundle_detail.html"):
            if "artifacts_page_obj" not in text:
                findings.append(f"{rel}: missing artifacts_page_obj wiring")

    meta_tpl = REPO / "templates/schools/super_metadata_catalog.html"
    if meta_tpl.is_file():
        meta_text = meta_tpl.read_text(encoding="utf-8")
        if '|slice:":10"' in meta_text:
            findings.append("super_metadata_catalog.html: hard field slice cap still present")
        if "field_preview" not in meta_text:
            findings.append("super_metadata_catalog.html: missing field_preview wiring")
        if "fields_overflow" not in meta_text:
            findings.append("super_metadata_catalog.html: missing fields_overflow disclosure")
    else:
        findings.append("missing templates/schools/super_metadata_catalog.html")

    for rel, needle in WAVE5_SERVICES:
        path = REPO / rel
        if not path.is_file():
            findings.append(f"missing {rel}")
            continue
        if needle not in path.read_text(encoding="utf-8"):
            findings.append(f"{rel}: missing {needle}")

    audit_json = REPO / "docs/generated/template_scroll_compression_audit.json"
    if not audit_json.is_file():
        findings.append("missing docs/generated/template_scroll_compression_audit.json")

    if findings:
        print("verify_scroll_compression_catalog_pagination: FAIL", file=sys.stderr)
        for item in findings:
            print(f"  - {item}", file=sys.stderr)
        return 1

    print(
        "verify_scroll_compression_catalog_pagination: "
        "SCROLL_COMPRESSION_CATALOG_PAGINATION_PASS"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
