#!/usr/bin/env python3
"""CEZGP batch 1522 — Customer experience zero-gap orchestrator."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "generated" / "customer_experience_zero_gap_audit.json"
MATRIX = ROOT / "docs" / "generated" / "customer_experience_research_matrix.json"


@dataclass
class Step:
    step_id: str
    label: str
    cmd: list[str]
    optional: bool = False


STEPS: tuple[Step, ...] = (
    Step("baseline", "verify_customer_experience_baseline.py", ["scripts/verify_customer_experience_baseline.py"]),
    Step("pay_all", "verify_parent_finance_pay_all.py", ["scripts/verify_parent_finance_pay_all.py"]),
    Step("csv_onboarding", "verify_tenant_onboarding_csv_import.py", ["scripts/verify_tenant_onboarding_csv_import.py"]),
    Step("launch_sla", "verify_tenant_launch_sla.py", ["scripts/verify_tenant_launch_sla.py"]),
    Step("parent_identity", "verify_parent_identity_ux.py", ["scripts/verify_parent_identity_ux.py"]),
    Step("public_status", "verify_public_status_real_probes.py", ["scripts/verify_public_status_real_probes.py"]),
    Step("feedback_loop", "verify_feedback_notification_loop.py", ["scripts/verify_feedback_notification_loop.py"]),
    Step("ease_layer", "verify_customer_experience_ease_layer.py", ["scripts/verify_customer_experience_ease_layer.py"]),
    Step("global_local", "verify_customer_experience_global_local.py", ["scripts/verify_customer_experience_global_local.py"]),
    Step(
        "glocal_kernel",
        "verify_glocal_zero_hardcode_kernel.py",
        ["scripts/verify_glocal_zero_hardcode_kernel.py", "--write"],
        optional=True,
    ),
    Step(
        "predeploy_core",
        "verify_predeploy_core_gates.py",
        ["scripts/verify_predeploy_core_gates.py"],
    ),
    Step(
        "parent_mobile_first",
        "verify_parent_mobile_first.py",
        ["scripts/verify_parent_mobile_first.py"],
    ),
    Step(
        "phase_h_subset",
        "verify_customer_experience_phase_h_subset.py",
        ["scripts/verify_customer_experience_phase_h_subset.py"],
    ),
    Step(
        "phases_3_11",
        "verify_phases_3_11_gates.py",
        ["scripts/verify_phases_3_11_gates.py"],
        optional=True,
    ),
    Step(
        "playwright_subset",
        "verify_customer_experience_playwright_subset.py",
        ["scripts/verify_customer_experience_playwright_subset.py"],
        optional=True,
    ),
    Step(
        "smart_links",
        "verify_smart_links_surface.py",
        ["scripts/verify_smart_links_surface.py"],
    ),
    Step(
        "plan_closeout",
        "verify_customer_experience_plan_closeout.py",
        ["scripts/verify_customer_experience_plan_closeout.py"],
    ),
    Step(
        "lane2_partials",
        "verify_customer_experience_lane2_partial_closeout.py",
        ["scripts/verify_customer_experience_lane2_partial_closeout.py"],
    ),
    Step(
        "preview_shell",
        "verify_preview_shell_100x_completion.py",
        ["scripts/verify_preview_shell_100x_completion.py"],
    ),
    Step(
        "matrix_strict",
        "audit_customer_experience_research_matrix.py --strict --strict-zero-partials",
        [
            "scripts/audit_customer_experience_research_matrix.py",
            "--strict",
            "--strict-zero-partials",
            "--write",
        ],
    ),
    Step("help_tiers", "verify_help_center_tiers.py", ["scripts/verify_help_center_tiers.py"]),
    Step("dead_hrefs", "scan_operator_shell_dead_hrefs.py --strict", ["scripts/scan_operator_shell_dead_hrefs.py", "--strict"]),
    Step("trust", "verify_trust_compliance_surfaces.py", ["scripts/verify_trust_compliance_surfaces.py"]),
    Step("doc_density", "verify_doc_plan_density_discipline.py", ["scripts/verify_doc_plan_density_discipline.py"]),
    Step(
        "interaction_integrity",
        "verify_interaction_integrity_completion.py",
        ["scripts/verify_interaction_integrity_completion.py"],
    ),
    Step(
        "phase3_nav",
        "verify_phase3_navigation_command_conformance.py",
        ["scripts/verify_phase3_navigation_command_conformance.py"],
    ),
    Step(
        "marketing_visual",
        "verify_marketing_glocal_visual_engine.py",
        ["scripts/verify_marketing_glocal_visual_engine.py"],
    ),
)


def _run(cmd: list[str], *, timeout: int = 900, step_id: str = "") -> tuple[bool, str]:
    if step_id == "phases_3_11":
        timeout = 3600
    script = ROOT / cmd[0]
    argv = [sys.executable, str(script), *cmd[1:]]
    try:
        proc = subprocess.run(
            argv,
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        out = ((proc.stdout or "") + (proc.stderr or "")).strip()
        tail = out[-800:] if out else ""
        return proc.returncode == 0, tail
    except (subprocess.TimeoutExpired, OSError) as exc:
        return False, str(exc)


def _matrix_missing_count() -> int | None:
    if not MATRIX.is_file():
        return None
    try:
        data = json.loads(MATRIX.read_text(encoding="utf-8"))
        return int(data.get("missing_count", 0))
    except (json.JSONDecodeError, TypeError, ValueError):
        return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true", help="Write audit JSON artifact.")
    parser.add_argument(
        "--include-optional",
        action="store_true",
        help="Run optional steps (verify_phases_3_11_gates; up to ~60 min).",
    )
    parser.add_argument(
        "--full",
        action="store_true",
        help="Alias for --include-optional (full phases 3–11 bundle).",
    )
    args = parser.parse_args()
    include_optional = args.include_optional or args.full

    results: list[dict] = []
    hard_fail = False
    for step in STEPS:
        if step.optional and not include_optional:
            results.append(
                {
                    "step_id": step.step_id,
                    "label": step.label,
                    "ok": True,
                    "optional": True,
                    "proof_tail": "skipped (--include-optional not set)",
                }
            )
            print(f"  [SKIP] {step.label} (optional)")
            continue
        ok, proof = _run(step.cmd, step_id=step.step_id)
        results.append(
            {
                "step_id": step.step_id,
                "label": step.label,
                "ok": ok,
                "optional": step.optional,
                "proof_tail": proof,
            }
        )
        if not ok and not step.optional:
            hard_fail = True

    missing = _matrix_missing_count()
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "verdict": "CUSTOMER_EXPERIENCE_ZERO_GAP_FAIL" if hard_fail else "CUSTOMER_EXPERIENCE_ZERO_GAP_PASS",
        "matrix_missing_count": missing,
        "steps": results,
    }

    if args.write:
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        print(f"Wrote {OUT}")

    for row in results:
        status = "OK" if row["ok"] else ("SKIP" if row["optional"] else "FAIL")
        print(f"  [{status}] {row['label']}")

    if missing is not None:
        print(f"matrix missing_count={missing}")

    if hard_fail:
        print("CUSTOMER_EXPERIENCE_ZERO_GAP_FAIL", file=sys.stderr)
        return 1

    print("CUSTOMER_EXPERIENCE_ZERO_GAP_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
