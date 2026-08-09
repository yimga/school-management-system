#!/usr/bin/env python3
"""Run named platform audit gates and print a pass/fail matrix (repo-scope)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# (label, command argv after python executable)
GATES: tuple[tuple[str, list[str]], ...] = (
    ("predeploy_core", ["scripts/verify_predeploy_core_gates.py"]),
    ("client_config_cascade", ["scripts/verify_client_config_cascade.py"]),
    ("dead_hrefs_strict", ["scripts/scan_operator_shell_dead_hrefs.py", "--strict"]),
    ("interaction_integrity", ["scripts/verify_interaction_integrity_completion.py"]),
    ("platform_action_click_contracts", ["scripts/verify_platform_action_click_contracts.py"]),
    ("luxury_baseline", ["scripts/verify_luxury_baseline_default.py"]),
    ("page_fold_standards", ["scripts/verify_page_fold_standards.py"]),
    ("template_comment_zero_leak", ["scripts/verify_template_comment_zero_leak.py"]),
    ("template_render_safety", ["scripts/audit_template_render_safety.py"]),
    ("platform_chromatic", ["scripts/verify_platform_chromatic_compliance.py"]),
    ("service_worker_monotonic", ["scripts/verify_service_worker_version.py", "--check-monotonic"]),
    ("platform_back_to_top", ["scripts/verify_platform_back_to_top.py"]),
    ("platform_layout_compact", ["scripts/verify_platform_layout_compact.py"]),
    ("five_pillar_platform", ["scripts/verify_five_pillar_platform_completion.py"]),
    ("unified_ai_assistant", ["scripts/verify_unified_ai_assistant.py"]),
    ("doc_plan_density", ["scripts/verify_doc_plan_density_discipline.py"]),
    # Tier 2 — CI architectural-boundaries subset (not in verify_phases_3_11_gates)
    ("tenant_queryset_safety", ["scripts/scan_tenant_queryset_safety.py", "--compare"]),
    ("tenant_isolation_markers", ["scripts/scan_tenant_isolation_marker_quality.py"]),
    ("security_surface", ["scripts/audit_security_surface.py"]),
    ("ai_gateway_boundary", ["scripts/scan_ai_gateway_boundary.py", "--compare"]),
    ("sentry_boundary", ["scripts/scan_sentry_boundary.py", "--compare"]),
    ("developer_public_surface", ["scripts/verify_developer_public_surface.py"]),
)


def _run(label: str, script_args: list[str]) -> tuple[str, int, str]:
    cmd = [sys.executable, str(ROOT / script_args[0]), *script_args[1:]]
    proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    tail = (proc.stdout or proc.stderr or "").strip().splitlines()
    hint = tail[-1] if tail else f"exit {proc.returncode}"
    status = "PASS" if proc.returncode == 0 else "FAIL"
    return label, proc.returncode, hint


def main() -> int:
    print("PLATFORM_AUDIT_BUNDLE — repo-scope gate matrix\n")
    failed: list[str] = []
    for label, args in GATES:
        _, code, hint = _run(label, args)
        mark = "PASS" if code == 0 else "FAIL"
        print(f"  [{mark}] {label}: {hint}")
        if code != 0:
            failed.append(label)

    print()
    if failed:
        print(f"PLATFORM_AUDIT_BUNDLE_FAIL ({len(failed)} gates): {', '.join(failed)}")
        return 1
    print(f"PLATFORM_AUDIT_BUNDLE_PASS ({len(GATES)} gates)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
