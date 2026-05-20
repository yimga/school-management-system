#!/usr/bin/env python3
"""Verify RunMyCampus orchestrator prompt pack is 100% complete.

Usage:
    python scripts/verify_orchestrator_prompt_pack.py [--strict] [--json]
    python scripts/generate_orchestrator_prompt_pack.py --write  # materialize missing files
"""
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROMPTS = ROOT / "docs" / "prompts"
MANIFEST = PROMPTS / "agent-assignment-index.json"
OUT = ROOT / "docs" / "generated" / "orchestrator_prompt_pack_audit.json"

STAGE_FILES_GEAR_UP = [
    "phase-0-p0-deploy-gate.md",
    "stage-00-current-state-validation.md",
    "stage-01-core-runtime.md",
    "stage-02-tenant-isolation.md",
    "stage-03-edge-routing-branding.md",
    "stage-04-policy-entitlements.md",
    "stage-05-finance-ledger.md",
    "stage-06-academics-operations.md",
    "stage-07-migration-cloud.md",
    "stage-08-workspace-ux.md",
    "stage-09-api-automation-base.md",
    "stage-09-ai-center-expanded.md",
    "stage-10-final-certification.md",
    "00-moderator-chief-orchestrator.md",
]

WORKER_PASTE_SLUGS = [
    "moderator",
    "agent0-stage-0",
    "agent1-stage-1",
    "agent2-stage-2",
    "agent3-stage-3",
    "agent4-stage-4",
    "agent5-stage-5",
    "agent6-stage-6",
    "agent7-stage-7",
    "agent8-stage-8",
    "agent9-stage-9",
    "agent10-stage-10",
]

REQUIRED_FILES = [
    "README.md",
    "00-global-execution-rules.md",
    "00-moderator-chief-orchestrator.md",
    "00-platform-wide-clause.md",
    "00-moderator-addendum.md",
    "00-gear-up-v3-escalation.md",
    "00-gear-up-v4-category-defining.md",
    "00-gear-up-v5-transformational.md",
    "phase-0-p0-deploy-gate.md",
    "stage-00-current-state-validation.md",
    "stage-01-core-runtime.md",
    "stage-02-tenant-isolation.md",
    "stage-03-edge-routing-branding.md",
    "stage-04-policy-entitlements.md",
    "stage-05-finance-ledger.md",
    "stage-06-academics-operations.md",
    "stage-07-migration-cloud.md",
    "stage-08-workspace-ux.md",
    "stage-09-api-automation-base.md",
    "stage-09-ai-center-expanded.md",
    "stage-10-final-certification.md",
    "pillar-prompts-01-07.md",
    "agent-assignment-index.json",
] + [f"worker-paste/{slug}.md" for slug in WORKER_PASTE_SLUGS]

STAGE_MARKERS: dict[str, list[str]] = {
    "stage-00-current-state-validation.md": [
        "READY FOR STAGE 1",
        "aggressive_stage_execution_readiness",
        "audit_route_surface",
    ],
    "stage-01-core-runtime.md": [
        "CORE RUNTIME READY",
        "core_runtime_dependency_audit",
        "test_cors_csrf_tenant_runtime",
    ],
    "stage-02-tenant-isolation.md": [
        "TENANT ISOLATION KERNEL READY",
        "tenant_kernel_architecture_review",
        "test_boundary_penetration",
    ],
    "stage-03-edge-routing-branding.md": [
        "EDGE SURFACES READY",
        "edge_surface_routing_audit",
        "four shell",
    ],
    "stage-04-policy-entitlements.md": [
        "CONFIGURATION POLICY ENGINE READY",
        "policy_entitlement_runtime_audit",
    ],
    "stage-05-finance-ledger.md": [
        "FINANCE LEDGER READY",
        "finance_ledger_precision_audit",
        "scan_money_float",
    ],
    "stage-06-academics-operations.md": [
        "ACADEMIC OPERATIONS READY",
        "academic_operations_workflow_audit",
    ],
    "stage-07-migration-cloud.md": [
        "MIGRATION CLOUD CONNECTORS READY",
        "migration_cloud_connector_certification",
        "CanonicalSchoolPayload",
    ],
    "stage-08-workspace-ux.md": [
        "WORKSPACE COCKPITS READY",
        "workspace_layout_constraint_audit",
    ],
    "stage-09-ai-center-expanded.md": [
        "FEATURE CODESPACE DISCONNECT",
        "DATA DEFAULTER",
        "ai/Modelfile",
        "RUNMYCAMPUS_AI_CENTER.md",
        "generate_ai_center_inventory",
        "PHASE 19",
        "API CENTER + AI CENTER READY",
        "test_ai_center_security",
    ],
    "stage-10-final-certification.md": [
        "ten_x_platform_certification",
        "10X PLATFORM READY",
        "75/75",
        "audit_admin_gravity.py --strict",
        "v3_compliance_pct",
        "v4_compliance_pct",
        "v5_compliance_pct",
        "journey_coverage_pct",
        "verify_orchestrator_v5_bundle",
    ],
    "00-moderator-chief-orchestrator.md": [
        "Chief Platform Orchestrator",
        "orchestrator_execution_matrix",
        "orchestrator_gap_burndown",
        "RERUN REQUIRED",
        "Stage 9",
        "Agent 10",
        "GEAR-UP V3",
        "Recovery wave",
    ],
    "00-gear-up-v3-escalation.md": [
        "GEAR-UP V3",
        "v3_delta",
        "75/75 ELITE",
        "audit_admin_gravity.py --strict",
    ],
    "00-gear-up-v4-category-defining.md": [
        "GEAR-UP V4",
        "ollama_live_proof",
        "v4_competitive_wins",
        "category-defining",
    ],
    "00-gear-up-v5-transformational.md": [
        "GEAR-UP V5",
        "orchestrator_journey_manifest",
        "TENANT_BASE_URL",
        "journey_coverage_pct",
    ],
    "phase-0-p0-deploy-gate.md": [
        "verify_migration_files_tracked",
        "bootstrap_at_risk_registry",
        "render_predeploy",
    ],
}


@dataclass
class Check:
    check_id: str
    ok: bool
    proof: str


def _read(rel: str) -> str:
    return (PROMPTS / rel).read_text(encoding="utf-8", errors="replace")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    checks: list[Check] = []
    min_bytes = 800 if not args.strict else 1200

    for name in REQUIRED_FILES:
        path = PROMPTS / name
        if not path.is_file():
            checks.append(Check(f"file:{name}", False, "missing"))
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        size_ok = len(text) >= min_bytes or name in {
            "00-platform-wide-clause.md",
            "00-moderator-addendum.md",
            "agent-assignment-index.json",
        }
        checks.append(
            Check(
                f"file:{name}",
                size_ok,
                f"{len(text)} bytes" if size_ok else f"too small ({len(text)} bytes)",
            )
        )
        for marker in STAGE_MARKERS.get(name, []):
            checks.append(
                Check(
                    f"marker:{name}:{marker[:40]}",
                    marker.lower() in text.lower(),
                    "found" if marker.lower() in text.lower() else "missing marker",
                )
            )

    for stage_name in STAGE_FILES_GEAR_UP:
        if not (PROMPTS / stage_name).is_file():
            continue
        stext = _read(stage_name)
        for layer in ("GEAR-UP V3", "GEAR-UP V4", "GEAR-UP V5"):
            checks.append(
                Check(
                    f"gear_up:{stage_name}:{layer}",
                    layer in stext,
                    "present" if layer in stext else f"missing {layer}",
                )
            )

    if MANIFEST.is_file():
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        agents = manifest.get("agents", [])
        checks.append(
            Check(
                "manifest:agents_count",
                len(agents) >= 11,
                f"{len(agents)} agents",
            )
        )
        for agent in agents:
            aid = agent.get("id", "?")
            prompt = agent.get("prompt_file", "")
            ok = (PROMPTS / prompt).is_file() if prompt else False
            checks.append(Check(f"manifest:agent:{aid}", ok, prompt or "no prompt_file"))
            wpaste = agent.get("worker_paste_file", "")
            wp_ok = (PROMPTS / wpaste).is_file() if wpaste else False
            checks.append(Check(f"manifest:worker_paste:{aid}", wp_ok, wpaste or "no worker_paste_file"))
            if wp_ok:
                wp_text = (PROMPTS / wpaste).read_text(encoding="utf-8")
                checks.append(
                    Check(
                        f"worker_paste:{aid}:has_global_rules",
                        "GLOBAL RUNMYCAMPUS EXECUTION RULES" in wp_text,
                        "global rules embedded",
                    )
                )
                checks.append(
                    Check(
                        f"worker_paste:{aid}:has_report_back",
                        "REPORT BACK TO ORCHESTRATOR" in wp_text,
                        "report-back block",
                    )
                )
                checks.append(
                    Check(
                        f"worker_paste:{aid}:has_gear_up_v3",
                        "GEAR-UP V3" in wp_text,
                        "gear-up v3 embedded",
                    )
                )
                checks.append(
                    Check(
                        f"worker_paste:{aid}:has_gear_up_v4",
                        "GEAR-UP V4" in wp_text,
                        "gear-up v4 embedded",
                    )
                )
                checks.append(
                    Check(
                        f"worker_paste:{aid}:has_gear_up_v5",
                        "GEAR-UP V5" in wp_text,
                        "gear-up v5 embedded",
                    )
                )
    else:
        checks.append(Check("manifest:exists", False, "missing agent-assignment-index.json"))

    # Stage 9 must be longer than base stub
    s9e = PROMPTS / "stage-09-ai-center-expanded.md"
    s9b = PROMPTS / "stage-09-api-automation-base.md"
    if s9e.is_file() and s9b.is_file():
        checks.append(
            Check(
                "stage9:expanded_gt_base",
                len(s9e.read_text()) > len(s9b.read_text()) + 5000,
                f"expanded={len(s9e.read_text())} base={len(s9b.read_text())}",
            )
        )

    fail = [c for c in checks if not c.ok]
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "prompt_pack_version": "2026-05-20-orchestrator-v5",
        "verdict": "ORCHESTRATOR_PROMPT_PACK_PASS" if not fail else "ORCHESTRATOR_PROMPT_PACK_FAIL",
        "pass_count": sum(1 for c in checks if c.ok),
        "fail_count": len(fail),
        "checks": [{"id": c.check_id, "ok": c.ok, "proof": c.proof} for c in checks],
        "failures": [c.check_id for c in fail],
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    if args.json:
        print(json.dumps(payload, indent=2))
    elif fail:
        print(f"ORCHESTRATOR_PROMPT_PACK_FAIL ({len(fail)} failures)")
        for c in fail[:30]:
            print(f"  - {c.check_id}: {c.proof}")
        if len(fail) > 30:
            print(f"  ... and {len(fail) - 30} more")
        print("Run: python scripts/generate_orchestrator_prompt_pack.py --write")
    else:
        print(
            f"ORCHESTRATOR_PROMPT_PACK_PASS ({payload['pass_count']} checks, "
            f"{len(REQUIRED_FILES)} files)"
        )
    return 1 if fail else 0


if __name__ == "__main__":
    raise SystemExit(main())
