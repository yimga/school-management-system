#!/usr/bin/env python3
"""Phase H depth gate: skip-link href targets must exist across platform shells (v2: expanded; 29 shells).

``--base`` resolves all template paths under the given repository root (default: this repository root).

Run: ``raise SystemExit(main(None))``.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# (template with skip-link href, fragment id, optional template where id lives if not in first file)
TARGET_SPECS: tuple[tuple[str, str, str | None], ...] = (
    ("templates/base.html", "main-content", None),
    ("templates/control_plane_skeleton.html", "cp-main-content", "templates/control_plane_base.html"),
    ("templates/portal_base.html", "main-content", None),
    ("templates/portal/kb_home.html", "kb-main-content", None),
    ("templates/admin/base_site.html", "content", "templates/admin/base.html"),
    ("templates/marketing/base_marketing.html", "main-content", None),
    ("templates/schools/marketing_landing.html", "hero", None),
    (
        "templates/schools/global_login_discovery.html",
        "global-login-discovery-main",
        None,
    ),
    (
        "templates/schools/super_runtime_truth_hub.html",
        "runtime-truth-hub-main",
        None,
    ),
    (
        "templates/schools/super_playbook_operator_hub.html",
        "playbook-operator-hub-main",
        None,
    ),
    (
        "templates/schools/super_phase_b_snapshot_diff.html",
        "phase-b-snapshot-diff-main",
        None,
    ),
    (
        "templates/schools/super_runtime_inspector.html",
        "runtime-inspector-main",
        None,
    ),
    (
        "templates/schools/super_workflow_simulator.html",
        "workflow-simulator-main",
        None,
    ),
    (
        "templates/schools/super_support_dashboard.html",
        "support-dashboard-main",
        None,
    ),
    (
        "templates/schools/super_support_csat_dashboard.html",
        "support-csat-dashboard-main",
        None,
    ),
    (
        "templates/schools/super_pulse.html",
        "super-pulse-main",
        None,
    ),
    (
        "templates/schools/super_usage.html",
        "super-usage-main",
        None,
    ),
    (
        "templates/schools/super_support_ticket_detail.html",
        "support-ticket-detail-main",
        None,
    ),
    (
        "templates/schools/super_tenant_health.html",
        "tenant-health-main",
        None,
    ),
    (
        "templates/schools/super_tenant_360.html",
        "tenant-360-main",
        None,
    ),
    (
        "templates/schools/super_command_center.html",
        "command-center-main",
        None,
    ),
    (
        "templates/orchestration/operator_workbench.html",
        "orchestration-workbench-main",
        None,
    ),
    (
        "templates/schools/super_dashboard.html",
        "super-dashboard-main",
        None,
    ),
    (
        "templates/schools/super_schools_list.html",
        "super-schools-list-main",
        None,
    ),
    (
        "templates/schools/super_analytics_overview.html",
        "analytics-overview-main",
        None,
    ),
    (
        "templates/schools/super_platform_operator_hub.html",
        "platform-operator-hub-main",
        None,
    ),
    (
        "templates/schools/super_migration_cloud.html",
        "migration-cloud-main",
        None,
    ),
    ("templates/schools/marketing_product_page.html", "mkt-product-hero", None),
    ("templates/studio_os/shell.html", "studio-canvas", None),
)


def _resolve_base(base: str) -> Path:
    root = Path(base).resolve()
    if not root.is_dir():
        raise ValueError(f"--base path does not exist or is not a directory: {base}")
    return root


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Phase H: verify skip-link href targets exist across platform shells."
    )
    parser.add_argument(
        "--base",
        default=str(ROOT),
        help="Repository root to inspect (default: this repository root).",
    )
    return parser.parse_args(argv)


def _read(root: Path, rel: str) -> str:
    return (root / rel).read_text(encoding="utf-8", errors="replace")


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        root = _resolve_base(args.base)
    except ValueError as exc:
        print(f"verify_phase_h_skiplink_targets: {exc}", file=sys.stderr)
        return 1

    errors: list[str] = []

    for rel, target, id_file in TARGET_SPECS:
        path = root / rel
        if not path.is_file():
            errors.append(f"Missing required template: {rel}")
            continue
        text = _read(root, rel)
        href_pat = re.compile(r'href=["\']#' + re.escape(target) + r'["\']')
        id_pat = re.compile(r'id=["\']' + re.escape(target) + r'["\']')
        if not href_pat.search(text):
            errors.append(f"{rel}: missing skip-link href '#{target}'")
        search_paths = [text]
        if id_file:
            ip = root / id_file
            if not ip.is_file():
                errors.append(f"{rel}: companion for target id missing: {id_file}")
            else:
                search_paths.append(_read(root, id_file))
        if any(id_pat.search(blob) for blob in search_paths):
            continue
        companion = f" (+ {id_file})" if id_file else ""
        errors.append(f"{rel}: missing target id '{target}'{companion}")

    if errors:
        print("verify_phase_h_skiplink_targets: FAIL", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        return 1

    print(
        "verify_phase_h_skiplink_targets: PASS "
        f"(skip-link targets resolve; {len(TARGET_SPECS)} shells)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(None))
