#!/usr/bin/env python3
"""Architecture deduplication audit for tenant lifecycle engines (Phase 3)."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
OUT_JSON = REPO_ROOT / "docs" / "generated" / "tenant_lifecycle_architecture_deduplication_audit.json"
OUT_MD = REPO_ROOT / "docs" / "generated" / "tenant_lifecycle_architecture_deduplication_audit.md"


def build() -> dict:
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "canonical": {
            "provisioning_execution": {
                "module": "apps/schools/tasks.py",
                "symbols": ["_do_provision", "provision_school_sync", "dispatch_provision_school"],
                "workflow_key": "tenant_school_provision",
            },
            "provisioning_progress": {
                "module": "apps/schools/provisioning_progress.py",
                "symbols": ["resolve_provisioning_progress"],
            },
            "operational_lifecycle": {
                "module": "apps/lifecycle/unified_lifecycle.py",
                "symbols": ["resolve_unified_lifecycle", "record_unified_transition"],
            },
            "lifecycle_spine": {
                "module": "apps/lifecycle/models.py",
                "symbols": ["SchoolLifecycleStage"],
            },
            "offboarding_execution": {
                "module": "apps/schools/tenant_offboarding.py",
                "symbols": ["run_wind_down_export", "apply_purge", "run_scheduled_purges"],
            },
            "offboarding_compliance": {
                "module": "apps/compliance/tenant_offboarding_inventory.py",
                "symbols": ["purge_public_school_dependencies", "drop_tenant_schema_for_school"],
            },
            "setup_studio_engine": {
                "module": "apps/setup_studio/wizard_engine.py",
                "symbols": ["WizardEngine"],
            },
        },
        "facades_compat": [
            {
                "module": "apps/lifecycle/services_offboarding.py",
                "role": "Soft-delete grace + audit mirror; wraps schools offboarding",
                "classification": "facade",
            },
            {
                "module": "apps/schools/onboarding_service.py",
                "role": "django-tenants schema migrate path; called from provision",
                "classification": "facade",
            },
            {
                "module": "apps/platform_runtime/tenant_lifecycle_engine.py",
                "role": "Read-only health phases for retention batch jobs",
                "classification": "read_only_analytics",
            },
            {
                "module": "apps/platform_runtime/tenant_lifecycle_state_machine.py",
                "role": "Marketing funnel states from MarketingFunnelEvent",
                "classification": "read_only_analytics",
            },
        ],
        "do_not_merge": [
            "platform_runtime growth states into unified_lifecycle operational FSM",
            "setup_studio wizard engine into provisioning tasks",
            "compliance purge inventory into schools.tenant_offboarding without boundary markers",
        ],
        "duplicate_risks": [
            {
                "risk": "create-school in legacy template + Setup Studio JSON",
                "mitigation": "super_views_create_school_wizard defaults to Setup Studio; ?legacy=1 escape hatch",
            },
            {
                "risk": "views_tenant_lifecycle in lifecycle vs platform_runtime",
                "mitigation": "Different URL namespaces; document in operator checklist",
            },
        ],
        "recommendation": "No engine deletion this pass; consolidate progress/notifications only.",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)
    data = build()
    if args.write:
        OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
        OUT_JSON.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        OUT_MD.write_text(
            "# Tenant lifecycle architecture deduplication audit\n\n"
            "Canonical provisioning: `apps/schools/tasks.py`. "
            "Canonical progress: `apps/schools/provisioning_progress.py`. "
            "Canonical operational FSM: `apps/lifecycle/unified_lifecycle.py`.\n",
            encoding="utf-8",
        )
        print(f"Wrote {OUT_JSON.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
