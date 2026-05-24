#!/usr/bin/env python3
"""One-shot: ensure phase4_pagination_targets carry data-rmc-scroll-policy=paginate."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REGISTRY = ROOT / "docs/generated/preview_shell_100x_parity_registry.json"

TARGETS = [
    "templates/schools/super_command_center.html",
    "templates/schools/super_dashboard.html",
    "templates/schools/super_security_hub.html",
    "templates/schools/super_education_systems.html",
    "templates/schools/super_migration_cloud.html",
    "templates/schools/super_phase_b_snapshot_diff.html",
    "templates/schools/super_playbook_operator_hub.html",
    "templates/schools/super_create_school_wizard.html",
    "templates/migration_cloud/super/health.html",
    "templates/feedback/school_center.html",
    "templates/platform_runtime/change_requests.html",
    "templates/platform_runtime/blueprint_marketplace.html",
    "templates/platform_runtime/pack_marketplace.html",
    "templates/schools/super_schools_list.html",
    "templates/schools/super_incidents_list.html",
    "templates/schools/super_billing_accounts_list.html",
    "templates/schools/super_feature_toggles_list.html",
    "templates/schools/super_country_multipliers_list.html",
    "templates/schools/super_tenant_360.html",
    "templates/schools/super_geography.html",
    "templates/schools/super_compliance_overview.html",
    "templates/schools/super_analytics_overview.html",
    "templates/schools/super_support_dashboard.html",
    "templates/schools/super_blueprints_catalog.html",
    "templates/schools/super_offboarding_queue.html",
    "templates/schools/super_migration_runs_list.html",
    "templates/schools/super_platform_events.html",
    "templates/schools/super_metadata_catalog.html",
    "templates/schools/super_ai_gateway_console.html",
    "templates/marketplace/governance_console.html",
]


def _inject(rel: str) -> bool:
    path = ROOT / rel
    if not path.is_file():
        return False
    text = path.read_text(encoding="utf-8")
    if 'data-rmc-scroll-policy="paginate"' in text:
        return False
    patterns = [
        (r'(<section[^>]*class="cp-page")', r'\1 data-rmc-scroll-policy="paginate"'),
        (
            r'(<div[^>]*id="command-center-main"[^>]*class="[^"]*)"',
            r'\1" data-rmc-scroll-policy="paginate"',
        ),
        (
            r'(<div class="container-fluid[^"]*)"([^>]*data-page-archetype)',
            r'\1" data-rmc-scroll-policy="paginate"\2',
        ),
        (
            r'(<main class="rmc-page[^"]*)"',
            r'\1" data-rmc-scroll-policy="paginate"',
        ),
        (
            r'({% block cp_content %}\s*\n\s*<section class="cp-page")',
            r'{% block cp_content %}\n<section class="cp-page" data-rmc-scroll-policy="paginate"',
        ),
    ]
    for pat, repl in patterns:
        new, n = re.subn(pat, repl, text, count=1)
        if n:
            path.write_text(new, encoding="utf-8")
            return True
    # fallback: first container-fluid in cp_content
    m = re.search(r"{% block cp_content %}.*?<div class=\"container-fluid", text, re.S)
    if m:
        idx = text.find('<div class="container-fluid', m.start())
        if idx >= 0:
            end = text.find(">", idx)
            if end >= 0 and "data-rmc-scroll-policy" not in text[idx : end + 1]:
                text = text[:end] + ' data-rmc-scroll-policy="paginate"' + text[end:]
                path.write_text(text, encoding="utf-8")
                return True
    return False


def main() -> int:
    data = json.loads(REGISTRY.read_text(encoding="utf-8"))
    data["phase4_pagination_targets"] = TARGETS
    REGISTRY.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    changed = 0
    for rel in TARGETS:
        if _inject(rel):
            changed += 1
            print(f"patched {rel}")
    print(f"apply_preview_shell_phase4_pagination_markers: {changed} files updated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
