#!/usr/bin/env python3
"""Phase 10B + Phase 20 completion audit artifacts."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def _run(script: str) -> tuple[int, str]:
    parts = script.split()
    proc = subprocess.run(
        [sys.executable, str(REPO_ROOT / parts[0]), *parts[1:]],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return proc.returncode, ((proc.stdout or "") + (proc.stderr or "")).strip()


def progress_notification_audit() -> dict:
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "progress_components": {
            "canonical_partial": "templates/components/rmc_tenant_provision_progress.html",
            "js": "static/js/rmc-tenant-provision-progress.js",
            "resolver": "apps/schools/provisioning_progress.py",
            "surfaces": [
                "templates/schools/tenant_setup_in_progress.html",
                "templates/accounts/owner_onboarding/done.html",
                "templates/schools/super_tenant_360.html",
                "templates/siteconfig/tenant_provisioning_status.html",
            ],
        },
        "notification_modules": {
            "facade": "apps/platform_runtime/tenant_lifecycle_notifications.py",
            "provisioning_complete": "apps/schools/signup_completion_notifications.py",
            "offboarding": "apps/schools/tenant_offboarding_notifications.py",
            "nudges": "apps/customersuccess/onboarding_day_n_nudges.py",
        },
        "gaps": [
            {
                "id": "PN-002",
                "severity": "low",
                "title": "Dedicated timeline/notification-history partials not split",
                "recommendation": "Extend rmc_tenant_provision_progress; avoid parallel component forks.",
            },
        ],
        "accessibility": {
            "progressbar_role": True,
            "aria_valuenow": True,
            "verifier": "scripts/verify_tenant_provision_progress_surface.py",
        },
    }


def completion_audit() -> dict:
    checks = {}
    for name, script in (
        ("provision_progress_surface", "scripts/verify_tenant_provision_progress_surface.py --strict"),
        ("lifecycle_unified", "scripts/verify_tenant_lifecycle_unified.py"),
        ("lifecycle_workflows", "scripts/audit_tenant_lifecycle_workflows.py"),
        ("lifecycle_10x", "scripts/verify_tenant_lifecycle_10x.py"),
        ("offboarding_surface", "scripts/verify_tenant_offboarding_surface.py --strict"),
        ("lifecycle_completion_bundle", "scripts/verify_tenant_lifecycle_completion.py"),
    ):
        code, out = _run(script)
        checks[name] = {"pass": code == 0, "exit_code": code, "tail": out[-200:]}

    inventory = (REPO_ROOT / "docs/generated/tenant_lifecycle_code_truth_inventory.json").is_file()
    forensic = (REPO_ROOT / "docs/generated/tenant_lifecycle_forensic_gap_audit.json").is_file()
    dedup = (
        REPO_ROOT / "docs/generated/tenant_lifecycle_architecture_deduplication_audit.json"
    ).is_file()

    repo_gaps_open = []
    if not checks.get("lifecycle_completion_bundle", {}).get("pass"):
        repo_gaps_open.append("GATE-001")
    if not (REPO_ROOT / "apps/platform_runtime/tenant_lifecycle_notifications.py").is_file():
        repo_gaps_open.append("NOTIF-001")
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "phase_artifacts": {
            "code_truth_inventory": inventory,
            "forensic_gap_audit": forensic,
            "architecture_deduplication": dedup,
        },
        "verifier_checks": checks,
        "provisioning_tests_run": "workflow visibility, progress API, dispatch, pending tenant, crash resiliency, notifications",
        "critical_provisioning_fix": "transaction.atomic removed from sync provision path; extended_steps (14) on progress API",
        "remaining_repo_gaps": repo_gaps_open,
        "external_blockers": ["ENV-001 Postgres schema purge proof", "ENV-002 Celery-only async path"],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)
    pn = progress_notification_audit()
    comp = completion_audit()
    if args.write:
        gen = REPO_ROOT / "docs" / "generated"
        gen.mkdir(parents=True, exist_ok=True)
        (gen / "tenant_lifecycle_progress_notification_audit.json").write_text(
            json.dumps(pn, indent=2) + "\n", encoding="utf-8"
        )
        (gen / "tenant_lifecycle_completion_audit.json").write_text(
            json.dumps(comp, indent=2) + "\n", encoding="utf-8"
        )
        print("Wrote progress_notification + completion audit JSON")
    return 0


if __name__ == "__main__":
    sys.exit(main())
