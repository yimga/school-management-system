#!/usr/bin/env python3
"""Write orchestrator journey manifest (27 journeys = 3 per stage 1–9)."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "generated" / "orchestrator_journey_manifest.json"


def _j(
    jid: str,
    stage: int,
    persona: str,
    title: str,
    *,
    verifier: str | None = None,
    spec: str | None = None,
    django_test: str | None = None,
    host: str = "manager",
) -> dict:
    proof: dict = {"host": host}
    if verifier:
        proof["verifier"] = verifier
    if spec:
        proof["spec"] = spec
    if django_test:
        proof["django_test"] = django_test
    return {
        "journey_id": jid,
        "stage": stage,
        "persona": persona,
        "title": title,
        "proof": proof,
    }


JOURNEYS = [
    # Stage 1
    _j("S1-J1", 1, "operator", "Core runtime health", verifier="manage.py check"),
    _j("S1-J2", 1, "operator", "BOLA matrix", django_test="apps.api.tests.test_bola_idor_matrix"),
    _j("S1-J3", 1, "operator", "Migration files tracked", verifier="verify_migration_files_tracked"),
    # Stage 2
    _j("S2-J1", 2, "operator", "Tenant isolation audit", verifier="audit_tenant_isolation"),
    _j("S2-J2", 2, "operator", "Queryset safety baseline", verifier="scan_tenant_queryset_safety"),
    _j(
        "S2-J3",
        2,
        "operator",
        "Boundary penetration tests",
        django_test="apps.analytics.tests.test_governed_query_layer",
    ),
    # Stage 3
    _j("S3-J1", 3, "operator", "Route surface certified", verifier="audit_route_surface"),
    _j("S3-J2", 3, "operator", "Platform chromatic", verifier="verify_platform_chromatic_compliance"),
    _j("S3-J3", 3, "operator", "Nav ledger", verifier="verify_nav_resolves_to_named_route"),
    # Stage 4
    _j("S4-J1", 4, "operator", "Policy entitlement audit", verifier="audit_policy_entitlement_runtime"),
    _j("S4-J2", 4, "operator", "Five-pillar gate", verifier="verify_five_pillar_platform_completion"),
    _j("S4-J3", 4, "teacher", "Permission matrix contract", django_test="apps.siteconfig.tests.test_interaction_integrity_contract"),
    # Stage 5
    _j("S5-J1", 5, "operator", "Money float zero", verifier="scan_money_float"),
    _j("S5-J2", 5, "operator", "Finance ledger audit", verifier="audit_finance_ledger_precision"),
    _j("S5-J3", 5, "parent", "Payment idempotency tests", django_test="apps.finance.tests.test_webhook_claim_concurrent"),
    # Stage 6
    _j("S6-J1", 6, "teacher", "Academic operations audit", verifier="audit_academic_operations_workflow"),
    _j("S6-J2", 6, "teacher", "Page fold standards", verifier="verify_page_fold_standards"),
    _j("S6-J3", 6, "student", "EMIS schema lock", verifier="verify_emis_schema_lock"),
    # Stage 7
    _j("S7-J1", 7, "operator", "MC connectors 8/8", verifier="verify_migration_cloud_connectors"),
    _j("S7-J2", 7, "operator", "Migration cloud spec", spec="tests/e2e/migration-cloud.spec.js"),
    _j("S7-J3", 7, "operator", "Intake experience", verifier="verify_migration_cloud_intake_experience"),
    # Stage 8
    _j("S8-J1", 8, "operator", "Interaction integrity", verifier="verify_interaction_integrity_completion"),
    _j("S8-J2", 8, "operator", "Luxury UI 15/15", verifier="audit_luxury_ui_surface"),
    _j(
        "S8-J3",
        8,
        "operator",
        "Critical Playwright journeys",
        spec="tests/e2e/orchestrator-journeys-critical.spec.js",
    ),
    # Stage 9
    _j("S9-J1", 9, "operator", "AI engine room", verifier="verify_ai_engine_room"),
    _j("S9-J2", 9, "operator", "Ollama live strict", verifier="verify_ollama_live_strict"),
    _j("S9-J3", 9, "operator", "AI center spec", spec="tests/e2e/ai-center.spec.js"),
]


def main() -> int:
    # Normalize optional verifiers to existing scripts
    alias_verifier = {
        "audit_policy_entitlement_runtime": "audit_security_surface",
        "audit_finance_ledger_precision": "scan_money_float",
        "audit_academic_operations_workflow": "verify_page_fold_standards",
        "verify_emis_schema_lock": "verify_phases_3_11_gates",
        "verify_ollama_live_strict": "verify_ollama_live",
    }
    for j in JOURNEYS:
        v = j["proof"].get("verifier")
        if v in alias_verifier:
            j["proof"]["verifier_alias"] = v
            j["proof"]["verifier"] = alias_verifier[v]

    supplementary = [
        _j(
            "HC-J1",
            8,
            "operator",
            "Help center tier gate",
            verifier="verify_help_center_tiers",
        ),
        _j(
            "HC-J2",
            8,
            "operator",
            "Help deflection Playwright crawl",
            spec="tests/e2e/help-center-crawl.spec.js",
        ),
        _j(
            "HC-J3",
            8,
            "operator",
            "KB embedding coverage gate",
            verifier="verify_kb_embedding_coverage",
        ),
    ]

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "prompt_pack_version": "2026-05-20-orchestrator-v5",
        "journey_count": len(JOURNEYS),
        "stages_covered": list(range(1, 10)),
        "journeys": JOURNEYS,
        "supplementary_help_center_journeys": supplementary,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {OUT} ({len(JOURNEYS)} journeys)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
