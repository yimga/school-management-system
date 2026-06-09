#!/usr/bin/env python3
"""Forensic tenant lifecycle gap audit artifact (Phase 2)."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
OUT_JSON = REPO_ROOT / "docs" / "generated" / "tenant_lifecycle_forensic_gap_audit.json"
OUT_MD = REPO_ROOT / "docs" / "generated" / "tenant_lifecycle_forensic_gap_audit.md"


def _gaps() -> list[dict]:
    return [
        {
            "id": "PROV-001",
            "severity": "critical",
            "scope": "repo-side",
            "status": "done",
            "title": "WorkflowRun invisible during sync provision (fake 5% progress)",
            "affected_files": ["apps/schools/tasks.py"],
            "failure_mode": "Outer transaction.atomic hid WorkflowRun until entire job committed; polls showed hardcoded 5%.",
            "fix": "Remove outer atomic from provision_school_sync and provision_school_task; pulse steps commit incrementally.",
            "tests": ["apps/schools/tests/test_provisioning_workflow_visibility.py"],
            "evidence": "test_begin_run_is_visible_to_progress_api_immediately",
        },
        {
            "id": "PROV-002",
            "severity": "high",
            "scope": "repo-side",
            "status": "done",
            "title": "Pending tenant setup UX showed wrong CTAs and blank progress",
            "affected_files": [
                "templates/schools/tenant_setup_in_progress.html",
                "apps/schools/pending_tenant_discovery.py",
            ],
            "failure_mode": "Continue setup / sign-in before portal ready; no live step train.",
            "fix": "Minimal shell, gated buttons, background kick, inline rmc_tenant_provision_progress.",
            "tests": ["apps/schools/tests/test_pending_tenant_discovery.py"],
        },
        {
            "id": "PROV-003",
            "severity": "medium",
            "scope": "repo-side",
            "status": "done",
            "title": "14-step provisioning progress model not fully mapped to UI labels",
            "affected_files": ["apps/schools/provisioning_progress.py", "apps/platform_runtime/workflow_registry.py"],
            "failure_mode": "UI showed 5 workflow steps only; operator model needs 14 canonical steps.",
            "fix": "resolve_provisioning_progress exposes extended_steps (14) alongside 5-step WorkflowRun train.",
            "tests": ["apps/schools/tests/test_provisioning_progress_api.py"],
        },
        {
            "id": "NOTIF-001",
            "severity": "medium",
            "scope": "repo-side",
            "status": "done",
            "title": "Lifecycle notification idempotency scattered",
            "affected_files": [
                "apps/platform_runtime/tenant_lifecycle_notifications.py",
                "apps/schools/signup_completion_notifications.py",
                "apps/schools/tenant_offboarding_notifications.py",
            ],
            "failure_mode": "Retry provision could duplicate operator alerts without unified audit.",
            "fix": "tenant_lifecycle_notifications facade with delivery status + school.settings lifecycle_notifications.",
            "tests": [
                "apps/platform_runtime/tests/test_tenant_lifecycle_notifications.py",
                "apps/schools/tests/test_tenant_provisioning_crash_resiliency.py",
            ],
        },
        {
            "id": "ARCH-001",
            "severity": "low",
            "scope": "repo-side",
            "status": "documented",
            "title": "Three lifecycle state vocabularies (intentional separation)",
            "affected_files": [
                "apps/lifecycle/unified_lifecycle.py",
                "apps/platform_runtime/tenant_lifecycle_engine.py",
                "apps/platform_runtime/tenant_lifecycle_state_machine.py",
            ],
            "failure_mode": "Operator confusion if docs not read; not a runtime bug.",
            "fix": "Keep unified_lifecycle as operational SOT; growth layers read-only.",
            "tests": ["apps/lifecycle/tests/test_unified_lifecycle.py"],
        },
        {
            "id": "ENV-001",
            "severity": "medium",
            "scope": "environment",
            "status": "blocked_external",
            "title": "Schema-per-tenant purge proof requires Postgres + django-tenants",
            "affected_files": ["apps/compliance/tenant_offboarding_inventory.py"],
            "failure_mode": "SQLite local dev cannot prove schema drop.",
            "fix": "Represent as contract + CI matrix job; do not fake on SQLite.",
            "tests": ["apps/compliance/tests/test_tenant_offboarding_inventory_purge.py"],
        },
        {
            "id": "ENV-002",
            "severity": "low",
            "scope": "environment",
            "status": "blocked_external",
            "title": "Celery worker required for async-only deploy paths",
            "affected_files": ["apps/schools/tasks.py"],
            "failure_mode": "Without worker, complete_provisioning_for_school sync fallback must run (implemented).",
            "fix": "Document; sync fallback already in complete_provisioning_for_school.",
            "tests": ["apps/schools/tests/test_provisioning_dispatch.py"],
        },
        {
            "id": "GATE-001",
            "severity": "medium",
            "scope": "repo-side",
            "status": "done",
            "title": "verify_tenant_lifecycle_completion blocked by shell scroll contract",
            "affected_files": ["scripts/audit_shell_scroll_contract.py", "templates/admin/base.html"],
            "failure_mode": "Full lifecycle completion bundle fails unrelated admin shell check.",
            "fix": "Fix admin back-to-top placement or split lifecycle completion bundle from scroll gate.",
            "tests": ["scripts/verify_tenant_lifecycle_completion.py"],
        },
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)
    gaps = _gaps()
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "finding_count": len(gaps),
        "critical_open": sum(
            1 for g in gaps if g["severity"] == "critical" and g["status"] not in ("fixed_uncommitted", "done")
        ),
        "gaps": gaps,
    }
    if args.write:
        OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
        OUT_JSON.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        md = ["# Tenant lifecycle forensic gap audit", "", f"Findings: **{len(gaps)}**", ""]
        for g in gaps:
            md.append(f"## {g['id']} — {g['title']} ({g['severity']}, {g['status']})")
            md.append(f"- Scope: {g['scope']}")
            md.append(f"- Files: `{', '.join(g['affected_files'][:3])}`")
            md.append(f"- Fix: {g['fix']}")
            md.append("")
        OUT_MD.write_text("\n".join(md), encoding="utf-8")
        print(f"Wrote {OUT_JSON.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
