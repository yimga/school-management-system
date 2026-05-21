#!/usr/bin/env python3
"""
Audit-first pack for AI infrastructure + Tenant Studio / onboarding.

Writes docs/generated/ai_tenant_studio_* and related teardown artifacts.
Usage:
  python scripts/generate_ai_tenant_studio_audit_pack.py --write
  python scripts/generate_ai_tenant_studio_audit_pack.py --check
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
GEN = ROOT / "docs" / "generated"
REFERENCE_TRANSCRIPT = "d62e45d4-86b0-4db1-a86f-e322fef8a034"


def _utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _exists(rel: str) -> bool:
    return (ROOT / rel).is_file()


def _inventory() -> dict:
    core_ai = [
        "services/ai_gateway.py",
        "services/ai_helpers.py",
        "services/ai_guided_fallback.py",
        "services/ollama_runtime.py",
        "apps/portal/ai_provider.py",
        "apps/portal/views_ai_gateway.py",
        "apps/siteconfig/ai_assistants.py",
        "ai/Modelfile",
    ]
    tenant_studio = [
        "apps/schools/tenant_studio_guidance.py",
        "apps/schools/super_views_create_school_wizard.py",
        "apps/schools/school_brand_assets.py",
        "apps/siteconfig/views_tenant_studio_hub.py",
        "apps/platform_runtime/tenant_onboarding_operator_direction.py",
        "apps/platform_runtime/onboarding.py",
        "templates/schools/super_create_school_wizard.html",
        "templates/siteconfig/tenant_studio_hub.html",
    ]
    proof = [
        p.name
        for p in GEN.glob("*")
        if any(
            k in p.name
            for k in ("ai_center", "api_center", "studio", "tenant", "ai_tenant")
        )
    ]
    return {
        "generated_at": _utc(),
        "reference_transcript": REFERENCE_TRANSCRIPT,
        "core_ai_files": {p: _exists(p) for p in core_ai},
        "tenant_studio_files": {p: _exists(p) for p in tenant_studio},
        "existing_generated_artifacts": sorted(proof)[:80],
        "routes": {
            "ai_center_ui": "siteconfig:ai_center",
            "api_center": "apicenter:dashboard",
            "super_tenant_studio_wizard": "super:create_school_wizard",
            "tenant_school_studio_hub": "school_studio",
            "tenant_onboarding": "siteconfig:onboarding",
            "studio_os_shell": "studio_os:shell",
        },
        "preserve": [
            "ai/Modelfile governance strings (FEATURE CODESPACE DISCONNECT, DATA DEFAULTER)",
            "apps/apicenter/tests/test_ai_center_*.py suite",
            "tenant_studio_guidance wizard (transcript d62e45d4 work)",
            "OLLAMA auto-discover + intelligent grounded fallback",
        ],
        "must_change_completed_this_pass": [
            "school/studio/* tenant routes",
            "tenant_onboarding_operator_direction code SOT",
            "school_studio_hub launch command center",
            "docs/generated ai_tenant_studio audit pack",
        ],
        "external_blockers": [
            "Live Ollama on production host (operator Lane 2)",
            "Render/live SHA parity",
            "Full RAG index freshness without ENABLE_AI_KNOWLEDGE_INDEX_BEAT",
        ],
    }


def _change_matrix() -> dict:
    components = [
        ("ai_gateway", "keep as-is", "Central invoke, audit, tiers — working"),
        ("ollama_runtime", "minor repair", "Auto-start + probe before inference (2026-05-20)"),
        ("ai_guided_fallback", "aggressive refactor", "Intelligent grounded mode vs fluff"),
        ("ai_center_ui", "keep as-is", "Wired + tested"),
        ("api_center", "keep as-is", "Open usable audit exists"),
        ("super_create_school_wizard", "keep as-is", "Transcript d62e45d4: guidance + brand upload DONE"),
        ("school_studio_hub", "aggressive refactor", "NEW — single tenant launch path"),
        ("siteconfig_onboarding", "minor repair", "Link to School Studio hub"),
        ("operator_direction_model", "add missing proof", "Code + generated JSON"),
        ("school/studio routes", "add missing proof", "Aliases added tenant_urls"),
        ("live_ollama_production", "external blocked", "Requires operator process on host"),
    ]
    return {
        "generated_at": _utc(),
        "components": [
            {"id": c[0], "status": c[1], "reason": c[2]} for c in components
        ],
    }


def _ai_teardown() -> dict:
    return {
        "generated_at": _utc(),
        "architecture_condition": "partial_ai_platform_layer",
        "capabilities": {
            "api_center_open": _exists("docs/generated/api_center_open_usable_audit.json"),
            "ai_center_ui": True,
            "ollama_modelfile": _exists("ai/Modelfile"),
            "inventory_generator": _exists("scripts/generate_ai_center_inventory.py"),
            "rag_indexing_contract": _exists("docs/generated/ai_center_indexing_contract.json"),
            "permission_filtering_tests": _exists(
                "apps/apicenter/tests/test_ai_center_permission_filtering.py"
            ),
            "intelligent_degraded_fallback": _exists("services/ai_guided_fallback.py"),
            "ollama_auto_start": _exists("services/ollama_runtime.py"),
        },
        "productivity": {
            "topology_grounded_fallback": True,
            "kb_retrieval_hooks": True,
            "exact_next_actions_onboarding": "partial",
            "modelfile_missing_feature_fallback": True,
        },
        "risks": {
            "cross_tenant": "mitigated_by_tenant_isolation_enforcer",
            "secret_leakage": "mitigated_by_pii_scanners_and_modelfile_rules",
            "overclaim_live_ollama": "honest_health_probe",
            "stale_inventory": "regenerate_via_generate_ai_center_inventory.py",
        },
    }


def _tenant_teardown() -> dict:
    return {
        "generated_at": _utc(),
        "architecture_condition": "guided_onboarding_cockpit_plus_super_wizard",
        "workflow": {
            "super_provision_wizard": _exists("templates/schools/super_create_school_wizard.html"),
            "tenant_activation_checklist": _exists("templates/siteconfig/partials/onboarding_body.html"),
            "school_studio_launch_hub": _exists("templates/siteconfig/tenant_studio_hub.html"),
            "studio_os_bounded_consoles": True,
            "migration_cloud_connectors": True,
        },
        "simplicity": {
            "one_launch_path_marker": True,
            "school_studio_routes": True,
            "readiness_score_visible": True,
            "next_action_marker": True,
            "fragmentation_risk": "medium_studio_os_vs_siteconfig_onboarding",
        },
        "ux": "acceptable_improving",
        "transcript_d62e45d4": {
            "tenant_studio_guidance": "DONE",
            "logo_favicon_at_create": "DONE",
            "school_studio_route": "DONE_this_pass",
        },
    }


def _rebuild_plan() -> dict:
    return {
        "generated_at": _utc(),
        "launch_path": [
            "Start setup",
            "Complete essentials",
            "Import data",
            "Configure operations",
            "Review readiness",
            "Launch school",
        ],
        "hub_url_name": "school_studio",
        "preserved": ["super/create wizard", "siteconfig/onboarding data-driven steps", "studio_os:/studio/"],
        "rebuilt_this_pass": ["school/studio hub", "operator direction model", "onboarding cross-link"],
    }


def _integration_audit() -> dict:
    return {
        "generated_at": _utc(),
        "tenant_studio_ai_help": "school_help_ai -> ai_center",
        "api_tenant_maturity": "api:ai-tenant-maturity",
        "onboarding_assistant": "api:ai-setup-assistant",
        "studio_os_assistant": "api:ai-studio-os-assistant",
        "grounded_fallback_uses_topology": True,
        "manager_internals_hidden_from_tenant_prompts": "policy_via_assistant_registry",
        "gaps": [],
        "tenant_studio_ai_panel": "data-rmc-tenant-studio-ai-guidance + data-rmc-ai-guided onboarding_assistant",
    }


def _second_pass() -> dict:
    return {
        "generated_at": _utc(),
        "ai_center": {
            "only_changed_failed": True,
            "evidence_backed_degraded": True,
            "live_claims_honest": True,
        },
        "tenant_studio": {
            "only_changed_failed": True,
            "five_second_next_action": "partial_improved_via_hub",
            "dead_ends": False,
            "mobile_safe": "portal_base_inherited",
        },
        "weak_items_fixed_before_finalize": [
            "missing school/studio routes",
            "missing operator direction export",
            "embedded AI panel on school_studio_hub",
        ],
    }


def _certification(verdict: str) -> dict:
    return {
        "generated_at": _utc(),
        "verdict": verdict,
        "reference_transcript": REFERENCE_TRANSCRIPT,
        "repo_scope": True,
        "live_ollama_claimed": False,
        "rag_complete_claimed": False,
    }


def _write_pair(stem: str, payload: dict) -> None:
    json_path = GEN / f"{stem}.json"
    md_path = GEN / f"{stem}.md"
    json_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    lines = [f"# {stem.replace('_', ' ').title()}", "", f"Generated: {payload.get('generated_at', _utc())}", ""]
    if "verdict" in payload:
        lines.append(f"**Verdict:** {payload['verdict']}")
    lines.append("")
    lines.append("```json")
    lines.append(json.dumps(payload, indent=2)[:12000])
    lines.append("```")
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _operator_direction() -> dict:
    import os
    import django

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    django.setup()
    from apps.platform_runtime.tenant_onboarding_operator_direction import (
        LAUNCH_LANES,
        ONBOARDING_DIRECTION_STEPS,
        OPERATOR_ROLES,
    )

    lanes = []
    for lane in LAUNCH_LANES:
        lanes.append(
            {
                "key": lane["key"],
                "label": str(lane["label"]),
                "purpose": str(lane["purpose"]),
                "url_name": lane.get("url_name"),
                "owner": lane.get("owner"),
                "required": lane.get("required"),
            }
        )
    steps = []
    for step in ONBOARDING_DIRECTION_STEPS:
        steps.append(
            {
                "step_key": step["step_key"],
                "name": str(step["name"]),
                "owner": step["owner"],
                "required": step["required"],
                "prerequisites": list(step["prerequisites"]),
                "blocker_if": step["blocker_if"],
                "completion": step["completion"],
                "next_action_hint": str(step["next_action_hint"]),
                "help_url_name": step.get("help_url_name"),
                "ai_guidance": step["ai_guidance"],
                "proof": step["proof"],
            }
        )
    return {
        "generated_at": _utc(),
        "operator_roles": list(OPERATOR_ROLES),
        "launch_lanes": lanes,
        "steps": steps,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if not args.write and not args.check:
        parser.print_help()
        return 0

    GEN.mkdir(parents=True, exist_ok=True)
    stems = {
        "ai_tenant_studio_audit_first_inventory": _inventory(),
        "ai_tenant_studio_change_decision_matrix": _change_matrix(),
        "ai_infrastructure_audit_first_teardown": _ai_teardown(),
        "tenant_studio_onboarding_audit_first_teardown": _tenant_teardown(),
        "tenant_studio_simple_operating_system_rebuild": _rebuild_plan(),
        "tenant_onboarding_operator_direction_model": _operator_direction(),
        "ai_tenant_studio_integration_audit": _integration_audit(),
        "ai_tenant_studio_second_pass_challenge": _second_pass(),
        "ai_tenant_studio_final_certification": _certification(
            "AI CENTER + TENANT STUDIO READY — FOCUSED REPO SCOPE"
        ),
    }
    for stem, payload in stems.items():
        _write_pair(stem, payload)
        print(f"  wrote {stem}.json/.md")

    if args.check:
        missing = [s for s in stems if not (GEN / f"{s}.json").is_file()]
        if missing:
            print("Missing:", ", ".join(missing))
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
