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
OPERATOR_COPILOT_CSS = ROOT / "static" / "css" / "rmc-cp-copilot-grid-lock.css"
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

HEAD_ONLY_PARTIALS = (
    TEMPLATES / "partials" / "control_plane_operator_brand_style.html",
    TEMPLATES / "partials" / "rmc_viewport_engine.html",
    TEMPLATES / "components" / "rum_beacon.html",
    TEMPLATES / "partials" / "rmc_conditional_feature_boot.html",
    TEMPLATES / "partials" / "rmc_deferred_stylesheet.html",
    TEMPLATES / "partials" / "rmc_tenant_tools_styles.html",
    TEMPLATES / "partials" / "rmc_operator_tools_styles.html",
)

BACKEND_SHELLS = (
    TEMPLATES / "backend_base_tenant.html",
    TEMPLATES / "backend_base_manager.html",
)

HEAD_OWNED_RUNTIME_CSS = (
    "rmc-portal-row-detail-drawer.css",
    "rmc-tour.css",
    "rmc-ai-mode-switch.css",
)

BODY_COMPONENT_STYLESHEET_BANS = (
    TEMPLATES / "components" / "contextual_feedback_widget.html",
)

CSRF_META_FIRST_SCRIPTS = (
    ROOT / "static" / "js" / "theme-preference-bootstrap.js",
    ROOT / "static" / "js" / "rmc-tour.js",
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
        if path.name == "super_support_live_console.html" and "block cp_preview_page_h1" not in text:
            findings.append(finding(path, "duplicate_base_page_h1_not_suppressed"))
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
        for stylesheet in HEAD_OWNED_RUNTIME_CSS:
            if text.count(stylesheet) != 1:
                findings.append(
                    finding(path, f"runtime_stylesheet_head_ownership:{stylesheet}")
                )

    portal_base = (TEMPLATES / "portal_base.html").read_text(
        encoding="utf-8", errors="replace"
    )
    for token in (
        'id="rmc-responsive-sidebar-terminal"',
        'max-width: 991.98px',
        '#portal-sidebar-col[data-shell-sidebar-mount="desktop"]',
        '#portalSidebar[data-shell-sidebar-mount="offcanvas"]:not(.show)',
    ):
        if token not in portal_base:
            findings.append(finding(TEMPLATES / "portal_base.html", f"mobile_sidebar_contract:{token}"))

    control_plane_skeleton = (TEMPLATES / "control_plane_skeleton.html").read_text(
        encoding="utf-8", errors="replace"
    )
    for token in (
        'id="rmc-cp-responsive-grid-critical"',
        "max-width:1024px",
        'grid-template-areas:"rmc-shell-h" "rmc-shell-cv" "rmc-shell-f"',
        ">.rmc-app-shell__sidebar",
    ):
        if token not in control_plane_skeleton:
            findings.append(
                finding(
                    TEMPLATES / "control_plane_skeleton.html",
                    f"operator_mobile_critical_contract:{token}",
                )
            )

    operator_grid_css = OPERATOR_COPILOT_CSS.read_text(
        encoding="utf-8", errors="replace"
    )
    for token in (
        "@media (max-width: 1024px)",
        "grid-template-columns: minmax(0, 1fr) !important;",
        ".rmc-app-shell:has(> .rmc-app-shell__copilot)",
        "display: none !important;",
    ):
        if token not in operator_grid_css:
            findings.append(finding(OPERATOR_COPILOT_CSS, f"operator_mobile_css_contract:{token}"))

    shell_runtime_flags = {
        "portal_row_detail_drawer_bundle.html": "rmc_row_drawer_css_in_head=True",
        "rmc_tour_bootstrap.html": "rmc_tour_css_in_head=True",
        "rmc_ai_chrome_page_data.html": "rmc_ai_mode_css_in_head=True",
    }
    for path in SHELL_TEMPLATES:
        text = path.read_text(encoding="utf-8", errors="replace")
        for include_name, flag in shell_runtime_flags.items():
            if include_name in text and flag not in text:
                findings.append(finding(path, f"runtime_stylesheet_flag_missing:{flag}"))

    for path in HEAD_ONLY_PARTIALS:
        text = path.read_text(encoding="utf-8", errors="replace").casefold()
        for body_tag in ("<div", "<main", "<section", "<article", "<p", "<span"):
            if body_tag in text:
                findings.append(finding(path, f"head_partial_contains_body_markup:{body_tag}"))

    for path in BODY_COMPONENT_STYLESHEET_BANS:
        text = path.read_text(encoding="utf-8", errors="replace").casefold()
        if '<link rel="stylesheet"' in text:
            findings.append(finding(path, "body_component_owns_stylesheet"))

    for path in CSRF_META_FIRST_SCRIPTS:
        text = path.read_text(encoding="utf-8", errors="replace")
        meta_lookup = 'document.querySelector(\'meta[name="csrf-token"]\')'
        cookie_lookup = "document.cookie.match"
        if meta_lookup not in text or cookie_lookup not in text:
            findings.append(finding(path, "csrf_resolution_contract_missing"))
        elif text.index(meta_lookup) > text.index(cookie_lookup):
            findings.append(finding(path, "csrf_cookie_precedes_request_bound_meta"))

    for path in BACKEND_SHELLS:
        text = path.read_text(encoding="utf-8", errors="replace").casefold()
        if "<h1" in text:
            findings.append(finding(path, "router_shell_owns_fallback_h1"))

    ownership_forbidden = {
        TEMPLATES / "platform_runtime" / "tenant_pack_setup.html": (
            "rmc-world-class-experience.css",
        ),
        TEMPLATES / "backend_base_tenant.html": ("tenant-command-workspace.css",),
        TEMPLATES / "partials" / "rmc_tenant_tools_styles.html": (
            "rmc-workflow-guidance.css",
        ),
        TEMPLATES / "partials" / "rmc_operator_tools_styles.html": (
            "rmc-workflow-guidance.css",
        ),
    }
    for path, forbidden_tokens in ownership_forbidden.items():
        text = path.read_text(encoding="utf-8", errors="replace")
        for token in forbidden_tokens:
            if token in text:
                findings.append(finding(path, f"duplicate_stylesheet_ownership:{token}"))

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
