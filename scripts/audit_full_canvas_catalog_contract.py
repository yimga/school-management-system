#!/usr/bin/env python3
"""Fail closed on the full-canvas operational-catalog layout contract.

This is deliberately source-level and complements browser/host render evidence.
It scans every operational workbench for the generic panel + grid + card defect
signature, then verifies the approved tenant-pack implementation and the six
operator findings discovered in the 2026-07-31 platform-wide audit.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "templates"
PACK_TEMPLATE = TEMPLATES / "platform_runtime" / "tenant_pack_setup.html"
PACK_CSS = ROOT / "static" / "css" / "rmc-tenant-pack-workbench.css"
APPROVAL = (
    ROOT
    / "var"
    / "design-previews"
    / "tenant-pack-setup-full-canvas-before-after-approval-2026-07-31.html"
)

OPERATOR_FRAME_TEMPLATES = (
    TEMPLATES / "schools" / "super_provision_queue.html",
    TEMPLATES / "schools" / "super_support_live_console.html",
)

WRAP_TEMPLATES = (
    TEMPLATES / "super" / "ai_line_intent_coverage.html",
    TEMPLATES / "super" / "merges" / "index.html",
    TEMPLATES / "super" / "school_batches" / "index.html",
    TEMPLATES / "super" / "transfers" / "cases_index.html",
)

SHELL_TEMPLATES = (
    TEMPLATES / "portal_base.html",
    TEMPLATES / "control_plane_skeleton.html",
    TEMPLATES / "base.html",
)


def rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def finding(path: Path, issue: str) -> dict[str, str]:
    return {"file": rel(path), "issue": issue}


def scan() -> dict[str, object]:
    findings: list[dict[str, str]] = []
    template_count = 0
    workbench_count = 0
    signature_count = 0

    for path in sorted(TEMPLATES.rglob("*.html")):
        template_count += 1
        text = path.read_text(encoding="utf-8", errors="replace")
        if (
            'data-page-archetype="operational-workbench"' not in text
            and 'data-rmc-operational-workbench="1"' not in text
        ):
            continue
        workbench_count += 1
        has_generic_signature = (
            'class="panel' in text
            and 'class="grid' in text
            and 'class="card' in text
        )
        if has_generic_signature:
            signature_count += 1
            findings.append(finding(path, "generic_panel_grid_card_collision"))

    if not PACK_TEMPLATE.exists():
        findings.append(finding(PACK_TEMPLATE, "tenant_pack_template_missing"))
    else:
        template = PACK_TEMPLATE.read_text(encoding="utf-8", errors="replace")
        required = (
            'data-rmc-full-canvas-catalog="tenant-pack"',
            'data-rmc-pack-inspector="1"',
            'data-rmc-genuine-pack-action="1"',
            "components/pagination.html",
            "rmc-tenant-pack-workbench.css",
            "world_class_readiness_meter.html",
        )
        for token in required:
            if token not in template:
                findings.append(finding(PACK_TEMPLATE, f"missing_contract:{token}"))
        for token in ('class="panel', 'class="grid', 'class="card', "page-shell"):
            if token in template:
                findings.append(finding(PACK_TEMPLATE, f"legacy_layout_token:{token}"))
        backend_pos = template.find("{% block backend_page %}")
        if backend_pos >= 0 and '<link rel="stylesheet"' in template[backend_pos:]:
            findings.append(finding(PACK_TEMPLATE, "stylesheet_link_owned_by_body"))

    if not PACK_CSS.exists():
        findings.append(finding(PACK_CSS, "tenant_pack_css_missing"))
    else:
        css = PACK_CSS.read_text(encoding="utf-8", errors="replace")
        for token in (
            '[data-rmc-tenant-pack-workbench="1"]',
            "grid-template-columns: minmax(0, 1fr) minmax(19rem, 28%);",
            "@media (max-width: 1024px)",
            "grid-template-columns: minmax(0, 1fr);",
            "max-inline-size: none !important;",
        ):
            if token not in css:
                findings.append(finding(PACK_CSS, f"missing_css_contract:{token}"))
        if "\n.grid" in css or "\n.card" in css or "\n.panel" in css:
            findings.append(finding(PACK_CSS, "unscoped_generic_selector"))

    if not APPROVAL.exists():
        findings.append(finding(APPROVAL, "approved_before_after_html_missing"))
    else:
        approval = APPROVAL.read_text(encoding="utf-8", errors="replace")
        for token in (
            "Tenant Pack Setup — full-canvas approval",
            'data-set-mode="before"',
            'data-set-mode="after"',
            'data-set-mode="audit"',
        ):
            if token not in approval:
                findings.append(finding(APPROVAL, f"approval_evidence_missing:{token}"))

    for path in OPERATOR_FRAME_TEMPLATES:
        text = path.read_text(encoding="utf-8", errors="replace")
        if "rmc_operational_center_frame.html" not in text:
            findings.append(finding(path, "operator_steering_frame_missing"))
        if "block cp_workspace_header" not in text:
            findings.append(finding(path, "duplicate_workspace_header_not_suppressed"))
        if "<h1" in text.casefold():
            findings.append(finding(path, "local_h1_duplicates_shared_frame"))

    for path in WRAP_TEMPLATES:
        text = path.read_text(encoding="utf-8", errors="replace")
        if "overflow: hidden" in text:
            findings.append(finding(path, "clipping_overflow_hidden"))
        if "overflow-wrap: anywhere" not in text:
            findings.append(finding(path, "long_value_wrap_missing"))

    for path in SHELL_TEMPLATES:
        text = path.read_text(encoding="utf-8", errors="replace")
        body_pos = text.casefold().find("<body")
        if body_pos >= 0 and 'rel="stylesheet"' in text[body_pos:]:
            findings.append(finding(path, "shell_stylesheet_link_in_body"))
        if text.count("rmc_theme_experience_dual_plane_styles.html") != 1:
            findings.append(finding(path, "duplicate_or_missing_terminal_theme_stylesheet"))

    support_partial = TEMPLATES / "partials" / "rmc_support_quick_create.html"
    support_text = support_partial.read_text(encoding="utf-8", errors="replace")
    if 'rel="stylesheet"' in support_text:
        findings.append(finding(support_partial, "runtime_partial_injects_stylesheet"))

    return {
        "template_count": template_count,
        "operational_workbench_count": workbench_count,
        "generic_signature_count": signature_count,
        "finding_count": len(findings),
        "findings": findings,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    payload = scan()
    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        print(
            "full-canvas-catalog: "
            f"{payload['template_count']} templates; "
            f"{payload['operational_workbench_count']} workbenches; "
            f"{payload['finding_count']} finding(s)"
        )
        for row in payload["findings"]:
            print(f"  {row['file']}: {row['issue']}")
    return 1 if args.strict and payload["findings"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
