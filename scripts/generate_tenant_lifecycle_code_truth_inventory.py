#!/usr/bin/env python3
"""Generate tenant lifecycle code-truth inventory (Phase 0 SOT artifact)."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
OUT_JSON = REPO_ROOT / "docs" / "generated" / "tenant_lifecycle_code_truth_inventory.json"
OUT_MD = REPO_ROOT / "docs" / "generated" / "tenant_lifecycle_code_truth_inventory.md"


def _glob_paths(pattern: str) -> list[str]:
    return sorted(
        str(p.relative_to(REPO_ROOT)).replace("\\", "/")
        for p in REPO_ROOT.glob(pattern)
        if p.is_file()
    )


def _exists(rel: str) -> bool:
    return (REPO_ROOT / rel).is_file()


def build_inventory() -> dict:
    now = datetime.now(timezone.utc).isoformat()
    verifiers = _glob_paths("scripts/*tenant*lifecycle*") + _glob_paths(
        "scripts/verify_tenant_*"
    )
    verifiers = sorted(set(verifiers))

    generated_existing = [
        p
        for p in (
            "docs/generated/system_closure_map.json",
            "docs/generated/omni_tenant_lifecycle_forensic_audit.json",
            "docs/generated/org_lifecycle_events_audit.json",
            "docs/generated/crm_lifecycle_gap_closure.json",
            "var/security-audit-baseline-single-lifecycle-writer.json",
        )
        if _exists(p)
    ]

    return {
        "generated_at": now,
        "repo_root": str(REPO_ROOT),
        "provisioning_entry_points": {
            "tasks": [
                "apps/schools/tasks.py",
                "apps/schools/onboarding_service.py",
                "apps/academics/structure_provisioning.py",
                "apps/finance/payment_provision.py",
                "apps/customers/repositories/schema_provisioning_repository.py",
            ],
            "views": [
                "apps/schools/super_views_create_school_wizard.py",
                "apps/schools/super_views_provisioning.py",
                "apps/schools/signup_views.py",
                "apps/schools/views_pending_provision.py",
                "apps/lifecycle/views_rapid_create.py",
                "apps/lifecycle/views_bulk.py",
                "apps/lifecycle/views_clone.py",
                "apps/lifecycle/views_jobs.py",
                "apps/lifecycle/views_tenant_lifecycle.py",
            ],
            "progress": [
                "apps/schools/provisioning_progress.py",
                "templates/components/rmc_tenant_provision_progress.html",
                "static/js/rmc-tenant-provision-progress.js",
            ],
            "commands": _glob_paths("apps/schools/management/commands/*tenant*")
            + _glob_paths("apps/schools/management/commands/*signup*")
            + _glob_paths("apps/schools/management/commands/activate_pending*"),
        },
        "create_school_wizard": {
            "routes": [
                "apps/schools/super_urls.py:super:create_school_wizard",
                "apps/setup_studio/wizards/super_create_school.json",
            ],
            "views": [
                "apps/schools/super_views_create_school_wizard.py",
                "apps/setup_studio/legacy_view_bridge.py",
                "apps/setup_studio/wizard_views.py",
            ],
            "templates": [
                "templates/schools/super_create_school_wizard.html",
                "templates/setup_studio/operator_wizard.html",
            ],
        },
        "signup_pending_flows": {
            "modules": [
                "apps/schools/signup_views.py",
                "apps/schools/pending_tenant_discovery.py",
                "apps/schools/views_pending_provision.py",
                "apps/schools/signup_completion_notifications.py",
                "apps/accounts/views_owner_onboarding.py",
            ],
            "templates": [
                "templates/schools/tenant_setup_in_progress.html",
                "templates/accounts/owner_onboarding/done.html",
                "templates/siteconfig/tenant_provisioning_status.html",
            ],
        },
        "setup_studio": {
            "core": [
                "apps/setup_studio/wizard_engine.py",
                "apps/setup_studio/services.py",
                "apps/setup_studio/wizard_views.py",
                "apps/setup_studio/tenant_guard.py",
            ],
            "wizard_json_count": len(_glob_paths("apps/setup_studio/wizards/*.json")),
            "templates": _glob_paths("templates/setup_studio/**/*.html")[:40],
        },
        "lifecycle_state_machines": {
            "operational_unified": "apps/lifecycle/unified_lifecycle.py",
            "spine_model": "apps/lifecycle/models.py",
            "product_phases": "apps/platform_runtime/tenant_lifecycle_engine.py",
            "funnel_states": "apps/platform_runtime/tenant_lifecycle_state_machine.py",
            "workflow_matrix": "apps/lifecycle/enrollment_workflow_matrix.py",
            "workflow_runs": "apps/platform_runtime/models_workflow_run.py",
            "provisioning_workflow_key": "tenant_school_provision",
        },
        "offboarding": {
            "core": [
                "apps/schools/tenant_offboarding.py",
                "apps/lifecycle/services_offboarding.py",
                "apps/compliance/tenant_offboarding_inventory.py",
                "apps/compliance/tenant_offboarding_storage.py",
                "apps/billing/offboarding.py",
                "apps/schools/tenant_offboarding_notifications.py",
            ],
            "views": [
                "apps/schools/super_views_tenant_offboarding.py",
                "apps/schools/super_views_offboarding_queue.py",
                "apps/schools/views_tenant_self_offboarding.py",
            ],
        },
        "tenancy_infra": [
            "apps/tenancy/middleware.py",
            "apps/tenancy/tasks.py",
            "apps/tenancy/context.py",
            "apps/tenancy/middleware_rls_jwt.py",
            "apps/tenancy/pool_readiness.py",
        ],
        "tests": {
            "lifecycle": len(_glob_paths("apps/lifecycle/**/test*.py")),
            "setup_studio": len(_glob_paths("apps/setup_studio/**/test*.py")),
            "schools_provision": len(_glob_paths("apps/schools/tests/test_*provision*.py")),
            "schools_offboard": len(_glob_paths("apps/schools/tests/test_*offboard*.py")),
            "schools_signup": len(_glob_paths("apps/schools/tests/test_*signup*.py")),
            "platform_runtime_lifecycle": len(
                _glob_paths("apps/platform_runtime/tests/test_tenant_lifecycle*.py")
            ),
        },
        "verifier_scripts": verifiers,
        "generated_artifacts": {
            "present": generated_existing,
            "missing_expected": [
                "docs/generated/tenant_lifecycle_code_truth_inventory.json",
                "docs/generated/tenant_lifecycle_forensic_gap_audit.json",
                "docs/generated/tenant_lifecycle_architecture_deduplication_audit.json",
                "docs/generated/tenant_lifecycle_progress_notification_audit.json",
                "docs/generated/tenant_lifecycle_completion_audit.json",
            ],
        },
        "canonical_engines": {
            "provisioning_execution": "apps/schools/tasks.py::_do_provision",
            "provisioning_progress": "apps/schools/provisioning_progress.py",
            "operational_lifecycle": "apps/lifecycle/unified_lifecycle.py",
            "offboarding_execution": "apps/schools/tenant_offboarding.py",
            "post_provision_config": "apps/setup_studio/wizard_engine.py",
            "growth_retention_readonly": "apps/platform_runtime/tenant_lifecycle_engine.py",
            "lifecycle_notifications": "apps/platform_runtime/tenant_lifecycle_notifications.py",
        },
        "phase_completion": {
            "crash_resiliency_tests": "apps/schools/tests/test_tenant_provisioning_crash_resiliency.py",
            "notification_facade_tests": "apps/platform_runtime/tests/test_tenant_lifecycle_notifications.py",
            "offboarding_adversarial_tests": "apps/schools/tests/test_tenant_offboarding_adversarial.py",
            "e2e_setup_progress": "tests/e2e/tenant-lifecycle-setup-progress.spec.js",
        },
    }


def render_md(inv: dict) -> str:
    lines = [
        "# Tenant lifecycle code-truth inventory",
        "",
        f"Generated: `{inv['generated_at']}`",
        "",
        "## Canonical engines",
        "",
    ]
    for k, v in inv["canonical_engines"].items():
        lines.append(f"- **{k}**: `{v}`")
    lines.extend(["", "## Test module counts", ""])
    for k, v in inv["tests"].items():
        lines.append(f"- {k}: **{v}**")
    lines.extend(["", "## Verifier scripts", ""])
    for s in inv["verifier_scripts"]:
        lines.append(f"- `{s}`")
    lines.extend(["", "## Setup Studio wizards", ""])
    lines.append(f"- JSON wizard count: **{inv['setup_studio']['wizard_json_count']}**")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)
    inv = build_inventory()
    if args.write:
        OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
        OUT_JSON.write_text(json.dumps(inv, indent=2) + "\n", encoding="utf-8")
        OUT_MD.write_text(render_md(inv), encoding="utf-8")
        print(f"Wrote {OUT_JSON.relative_to(REPO_ROOT)}")
        print(f"Wrote {OUT_MD.relative_to(REPO_ROOT)}")
    else:
        print(json.dumps(inv, indent=2)[:2000])
    return 0


if __name__ == "__main__":
    sys.exit(main())
