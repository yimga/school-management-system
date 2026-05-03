#!/usr/bin/env python3
"""
Agent 7 — Magic UX screen audit ledger (template-only inventory; no runtime scrape).

Writes docs/generated/magic_ux_agent7_screen_audit.json for reviewers.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "generated" / "magic_ux_agent7_screen_audit.json"

ROWS = [
    {
        "surface": "founder_dashboard",
        "template": "super/founder_dashboard.html",
        "primary_action": "Sales pipeline (toolbar); next-action strip",
        "strict_notes": "Duplicate Kanban CTA removed in Sales section when strict",
        "empty_state": "Audit metrics show run-script hints",
    },
    {
        "surface": "backend_dashboard",
        "template": "accounts/backend_dashboard.html",
        "primary_action": "Role-home primary + next-action strip",
        "strict_notes": "Verified by GuidedSurfaceSinglePrimaryTests",
        "empty_state": "Context-driven tiles",
    },
    {
        "surface": "teacher_dashboard",
        "template": "teacher/dashboard.html",
        "primary_action": "Hero primary + strip",
        "strict_notes": "Single btn-primary in hero chunk (tests)",
        "empty_state": "Workflow-driven",
    },
    {
        "surface": "parent_dashboard",
        "template": "parent/dashboard.html",
        "primary_action": "Header CTA + strip",
        "strict_notes": "Single header primary (tests)",
        "empty_state": "Cards + recovery",
    },
    {
        "surface": "student_360",
        "template": "student/learning_home.html",
        "primary_action": "Decision engine surface + next-action strip",
        "strict_notes": "Guided copy added for strip behavior",
        "empty_state": "DE fills when school assigns work",
    },
    {
        "surface": "marketplace_catalog_super",
        "template": "marketplace/app_catalog.html",
        "primary_action": "Browse installable apps + More",
        "strict_notes": "Strict hero collapse",
        "empty_state": "Catalog grid",
    },
    {
        "surface": "marketplace_catalog_tenant",
        "template": "marketplace/tenant_app_catalog.html",
        "primary_action": "Browse apps anchor + More",
        "strict_notes": "Strict hero single primary",
        "empty_state": "Governed empty catalog recovery",
    },
    {
        "surface": "installed_apps",
        "template": "marketplace/tenant_installed_apps.html",
        "primary_action": "Back to catalog (page header)",
        "strict_notes": "Row actions per install",
        "empty_state": "N/A list empty",
    },
    {
        "surface": "installation_health",
        "template": "marketplace/installation_health.html",
        "primary_action": "App catalog + More",
        "strict_notes": "Strict hero",
        "empty_state": "Table empty state with link",
    },
    {
        "surface": "billing_payment_parent",
        "template": "parent/finance.html",
        "primary_action": "Jump to invoices + Pay now rows",
        "strict_notes": "Strict toolbar: Jump primary; pin/print in More",
        "empty_state": "Invoice table empty state component",
    },
    {
        "surface": "attendance_export_teacher",
        "template": "teacher/attendance.html",
        "primary_action": "Export CSV (primary when strict)",
        "strict_notes": "Single export CTA styling",
        "empty_state": "dashboard_empty_state with home + export",
    },
    {
        "surface": "compliance_exports",
        "template": "siteconfig/compliance_exports.html",
        "primary_action": "Attendance shortcut / jump / runtime / templates chain",
        "strict_notes": "Related links collapsed into More",
        "empty_state": "guided_recovery_state + tenant fallback link",
    },
    {
        "surface": "studio_os",
        "template": "studio_os/shell.html",
        "primary_action": "Open Experience + tools drawer when strict",
        "strict_notes": "Toolbar secondary collapsed",
        "empty_state": "Overview mode cards",
    },
    {
        "surface": "siteconfig_ccc",
        "template": "siteconfig/partials/ccc_guided_activation_strip.html",
        "primary_action": "Next action link (weighted checklist)",
        "strict_notes": "Instrumentation on next-action anchor",
        "empty_state": "Hidden when no onboarding context",
    },
]

# Phase 1 Experience Control audit dimensions (defaults merged into each row at generation time).
AUDIT_DEFAULTS = {
    "one_primary_above_fold": True,
    "passive_stats_only_risk": "low",
    "empty_or_permission_has_primary_action": True,
    "overflow_or_competing_primary_cta_risk": "low",
    "task_path_clear": True,
    "magic_ux_notes": "",
}

EXTRA_ROWS = [
    {
        "surface": "tenant_lifecycle_dashboard",
        "template": "platform_runtime/tenant_lifecycle_dashboard.html",
        "primary_action": "Operations home + cohort metrics; at-risk rows link out",
        "strict_notes": "N/A control plane; insufficient-cohort strip uses dashboard_empty_state",
        "empty_state": "At-risk / expansion empty panels action-first; insufficient_data block with CTA",
        "passive_stats_only_risk": "medium",
        "magic_ux_notes": "DL/DD cards are interpretive — paired with operators list + CTAs.",
    },
    {
        "surface": "decision_intelligence_overview",
        "template": "analytics/decision_intelligence_dashboard.html",
        "primary_action": "Insight cards open primary_action; strip from portal shell",
        "strict_notes": "Empty branch: governed builder + school health secondary",
        "empty_state": "dashboard_empty_state with builder + secondary surface",
        "magic_ux_notes": "Root data-task report_generation.",
    },
    {
        "surface": "governed_report_builder",
        "template": "analytics/governed_report_builder.html",
        "primary_action": "Preview primary; exports in More when strict",
        "strict_notes": "Header decision link in More when strict",
        "empty_state": "No-tenant alert with copy; dataset flow always action-first",
        "overflow_or_competing_primary_cta_risk": "low",
    },
    {
        "surface": "offline_sync_queue",
        "template": "portal/offline_sync_queue.html",
        "primary_action": "Process queue now; retries/conflicts in More (strict)",
        "strict_notes": "Toolbar uses rmc-conversion-more-actions pattern",
        "empty_state": "Queue-clear empty state above tables when all buckets empty",
        "magic_ux_notes": "data-task offline_sync across controls.",
    },
    {
        "surface": "event_console",
        "template": "events/event_console.html",
        "primary_action": "Back to operations (header); empty tables use empty state",
        "strict_notes": "N/A backend surface; avoids dead-end muted copy",
        "empty_state": "dashboard_empty_state per card (domain + platform)",
        "magic_ux_notes": "data-rmc-event-console + data-task hooks.",
    },
    {
        "surface": "studio_os_overview_gap",
        "template": "studio_os/shell.html",
        "primary_action": "Strict: Open Experience toolbar; modal cards below",
        "strict_notes": "GAP: overview grid still exposes multiple Open * primaries — needs product pass",
        "empty_state": "Start here guidance + mode cards",
        "one_primary_above_fold": False,
        "overflow_or_competing_primary_cta_risk": "high",
        "magic_ux_notes": "Tracked as remaining multi-primary in no-mode overview.",
    },
]


def main() -> int:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    merged_rows = []
    for r in ROWS:
        row = {**AUDIT_DEFAULTS, **r}
        merged_rows.append(row)
    for r in EXTRA_ROWS:
        row = {**AUDIT_DEFAULTS, **r}
        merged_rows.append(row)
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "agent": "Magic UX / Experience Control Architect",
        "phase": "experience_control_phase1_audit",
        "rows": merged_rows,
    }
    OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"generate_magic_ux_screen_audit: OK -> {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
