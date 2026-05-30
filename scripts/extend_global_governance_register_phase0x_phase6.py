#!/usr/bin/env python3
"""Extend the global governance completion register with Phase 0X gap-closure IDs and Phase 6 turbocharge IDs.

Idempotent: skips IDs already present. Run after plan frontmatter is updated.
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

LOGGER = logging.getLogger("extend_register")

REPO = Path(__file__).resolve().parents[1]
REGISTER_PATH = REPO / "docs" / "generated" / "global_governance_completion_register.json"


PHASE_0X_ITEMS: list[dict[str, Any]] = [
    {
        "id": "P0X-regulatory-matrices",
        "phase": "0X",
        "title": "Per-country regulatory_matrix block (privacy / age-of-consent / biometric / AI / SMS / tax / sanctions / retention / content-safety / accessibility)",
        "agent_lane": "AUDIT",
        "proof": "python scripts/verify_regulatory_matrix_coverage.py",
    },
    {
        "id": "P0X-edge-jurisdictions",
        "phase": "0X",
        "title": "Edge jurisdictions register (unrecognized / disputed states, microstates, online-only, refugee / nomadic ed)",
        "agent_lane": "AUDIT",
        "proof": "python scripts/verify_edge_jurisdiction_coverage.py",
    },
    {
        "id": "P0X-data-lineage-versioning",
        "phase": "0X",
        "title": "Primary-source citations + time-versioning on every matrix field (effective_from / effective_to / verified_at / verified_by)",
        "agent_lane": "AUDIT",
        "proof": "python scripts/verify_matrix_provenance.py",
    },
    {
        "id": "P0X-org-lifecycle-events",
        "phase": "0X",
        "title": "Organization lifecycle event model (split / merge / dissolve / change-of-control / school-moves-org / bankruptcy / regulator-export)",
        "agent_lane": "GOV",
        "proof": "python scripts/verify_org_lifecycle_events.py",
    },
    {
        "id": "P0X-exam-boards-matrix",
        "phase": "0X",
        "title": "Exam-board integration matrix (Cambridge / IB / AQA / Edexcel / WAEC / KNEC / ICSE / CBSE / CollegeBoard / IBO / national exit-exam codes)",
        "agent_lane": "EMIS",
        "proof": "python scripts/verify_exam_board_coverage.py",
    },
    {
        "id": "P0X-legacy-mis-map",
        "phase": "0X",
        "title": "Legacy MIS incumbent map per country with migration-cloud route status",
        "agent_lane": "GEO",
        "proof": "python scripts/verify_legacy_mis_route_coverage.py",
    },
    {
        "id": "P0X-national-identity-sso",
        "phase": "0X",
        "title": "National identity / SSO federation matrix (eIDAS / NAFATH / DigiLocker / GOV.UK / SingPass / etc.)",
        "agent_lane": "RUNTIME",
        "proof": "python scripts/verify_national_sso_brokers.py",
    },
    {
        "id": "P0X-calendars-holidays-religious",
        "phase": "0X",
        "title": "Public-holiday + lunar / solar / religious calendar ingestion per country",
        "agent_lane": "LOCALE",
        "proof": "python scripts/verify_calendar_ingestion.py",
    },
    {
        "id": "P0X-labor-law-matrix",
        "phase": "0X",
        "title": "Labor-law matrix per country (employer-of-record / payroll authority / working-time / severance / collective bargaining)",
        "agent_lane": "GOV",
        "proof": "python scripts/verify_labor_law_matrix.py",
    },
    {
        "id": "P0X-minority-language-rights",
        "phase": "0X",
        "title": "Regional / minority language rights beyond constitutional (Welsh / Catalan / Quechua / Amazigh / etc.)",
        "agent_lane": "LOCALE",
        "proof": "python scripts/verify_minority_language_rights.py",
    },
    {
        "id": "P0X-accessibility-statutes",
        "phase": "0X",
        "title": "Accessibility statute matrix (WCAG 2.2 AA baseline + Section 508 / EAA / RGAA / JIS X 8341 / Equality Act / AODA) + sign-language metadata",
        "agent_lane": "AUDIT",
        "proof": "python scripts/verify_accessibility_matrix.py",
    },
    {
        "id": "P0X-dr-rto-rpo-residency",
        "phase": "0X",
        "title": "Disaster-recovery RTO / RPO per residency region + cross-region failover decision matrix",
        "agent_lane": "OPS",
        "proof": "python scripts/verify_dr_rto_rpo_residency.py",
    },
    {
        "id": "P0X-pricing-ppp-fx",
        "phase": "0X",
        "title": "Purchasing-power-parity pricing matrix per country with FX hedge band",
        "agent_lane": "FINANCE",
        "proof": "python scripts/verify_pricing_ppp_matrix.py",
    },
    {
        "id": "P0X-risk-register-quantified",
        "phase": "0X",
        "title": "Quantified risk register (probability x impact x detectability) with mitigation owner per ISO row",
        "agent_lane": "AUDIT",
        "proof": "python scripts/verify_risk_register.py",
    },
    {
        "id": "P0X-rollback-criteria-per-phase",
        "phase": "0X",
        "title": "Per-phase rollback runbook + safe-revert procedure (P0D / P1 / P2C / P3E / P4G / P5)",
        "agent_lane": "AUDIT",
        "proof": "python scripts/verify_rollback_runbooks.py",
    },
    {
        "id": "P0X-customer-comms-migration",
        "phase": "0X",
        "title": "Customer communications plan for Phase-2 org rollout (templates per residency / language)",
        "agent_lane": "PRODUCT",
        "proof": "python scripts/verify_customer_comms_templates.py",
    },
    {
        "id": "P0X-telemetry-slo-per-phase",
        "phase": "0X",
        "title": "Telemetry / SLO budget per phase (matrix-driven runtime, EMIS export, language overlay)",
        "agent_lane": "OPS",
        "proof": "python scripts/verify_phase_slo_budgets.py",
    },
    {
        "id": "P0X-property-tests-governance",
        "phase": "0X",
        "title": "Property-based tests over governance invariants (tenant isolation at any depth, inheritance idempotence)",
        "agent_lane": "AUDIT",
        "proof": "python scripts/verify_governance_property_tests.py",
    },
]


PHASE_6_ITEMS: list[dict[str, Any]] = [
    {
        "id": "P6-agentic-self-healing-matrix",
        "phase": "6",
        "title": "Agentic self-healing matrix (watcher agents on gazette / regulator feeds, <72h SLA on changes)",
        "agent_lane": "AUDIT",
        "proof": "python scripts/verify_matrix_freshness.py",
    },
    {
        "id": "P6-formal-verification-tla",
        "phase": "6",
        "title": "TLA+ specs for governance invariants (tenant isolation across org depth, role escalation, transcript forgery)",
        "agent_lane": "AUDIT",
        "proof": "python scripts/verify_tla_specs.py",
    },
    {
        "id": "P6-realtime-compliance-engine",
        "phase": "6",
        "title": "Real-time global compliance engine (country x subdivision x sector x grade jurisdiction stack)",
        "agent_lane": "RUNTIME",
        "proof": "python scripts/verify_compliance_engine.py",
    },
    {
        "id": "P6-sovereignty-trust-score",
        "phase": "6",
        "title": "Live per-country sovereignty trust score (infra residency x key custody x regulator API x counsel signoff)",
        "agent_lane": "GOV",
        "proof": "python scripts/verify_sovereignty_trust_score.py",
    },
    {
        "id": "P6-cross-vertical-kernel",
        "phase": "6",
        "title": "Abstract Tenant / Org / Governance / ContextProfile kernel for cross-vertical lift + alternate-vertical smoke pack",
        "agent_lane": "GOV",
        "proof": "python scripts/verify_cross_vertical_kernel.py",
    },
    {
        "id": "P6-multimodal-terminology",
        "phase": "6",
        "title": "Multi-modal terminology (audio / transliteration / sign-language) across 249 codes for top-K terms",
        "agent_lane": "LOCALE",
        "proof": "python scripts/verify_multimodal_terminology.py",
    },
    {
        "id": "P6-regulator-api-federation",
        "phase": "6",
        "title": "Live regulator API federation (X-Road / DigiLocker / GIAS / NCES / MOE / NAFATH / SACE)",
        "agent_lane": "RUNTIME",
        "proof": "python scripts/verify_regulator_api_federation.py",
    },
    {
        "id": "P6-adversarial-redteam",
        "phase": "6",
        "title": "Nightly adversarial red-team agent (BOLA / IDOR / tenant-leak / role-escalation / context-profile-confusion)",
        "agent_lane": "AUDIT",
        "proof": "python scripts/verify_adversarial_redteam.py",
    },
    {
        "id": "P6-w3c-verifiable-credentials",
        "phase": "6",
        "title": "W3C Verifiable Credentials for StudentPassport + transcripts (DID method per country)",
        "agent_lane": "GOV",
        "proof": "python scripts/verify_w3c_verifiable_credentials.py",
    },
    {
        "id": "P6-time-traveling-matrix",
        "phase": "6",
        "title": "Bitemporal time-versioned matrix (effective_from / effective_to bitemporal queries)",
        "agent_lane": "AUDIT",
        "proof": "python scripts/verify_time_traveling_matrix.py",
    },
    {
        "id": "P6-zero-form-bootstrap",
        "phase": "6",
        "title": "60-second zero-form tenant bootstrap from GeoIP + matrix row (sector / archetype / languages / EMIS / payments)",
        "agent_lane": "RUNTIME",
        "proof": "python scripts/verify_zero_form_bootstrap.py",
    },
    {
        "id": "P6-ai-policy-copilot",
        "phase": "6",
        "title": "AI policy copilot answering natural-language compliance questions with statute citation from matrix",
        "agent_lane": "PRODUCT",
        "proof": "python scripts/verify_ai_policy_copilot.py",
    },
    {
        "id": "P6-cross-org-marketplace",
        "phase": "6",
        "title": "Cross-org talent + curriculum marketplace (ReBAC-gated, per-org sharing flags)",
        "agent_lane": "PRODUCT",
        "proof": "python scripts/verify_cross_org_marketplace.py",
    },
    {
        "id": "P6-federated-emis-aggregator",
        "phase": "6",
        "title": "Federated EMIS aggregator with differential-privacy noise budget at school edge",
        "agent_lane": "EMIS",
        "proof": "python scripts/verify_federated_emis_aggregator.py",
    },
    {
        "id": "P6-living-competitor-tracker",
        "phase": "6",
        "title": "Living competitor tracker (weekly scrape of FACTS / PowerSchool / Arbor / iSAMS release notes; gap delta to product lane)",
        "agent_lane": "PRODUCT",
        "proof": "python scripts/verify_competitor_tracker.py",
    },
]


def _normalize(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": item["id"],
        "phase": item["phase"],
        "title": item["title"],
        "agent_lane": item["agent_lane"],
        "status": "NOT_DONE",
        "proof": item["proof"],
        "sot_batch": None,
        "blocked_reason": None,
    }


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    if not REGISTER_PATH.is_file():
        LOGGER.error("missing register at %s", REGISTER_PATH.relative_to(REPO))
        return 1

    register = json.loads(REGISTER_PATH.read_text(encoding="utf-8"))
    items: list[dict[str, Any]] = list(register.get("items") or [])
    existing_ids = {str(it.get("id") or "") for it in items}

    new_items = PHASE_0X_ITEMS + PHASE_6_ITEMS
    added = 0
    for spec in new_items:
        if spec["id"] in existing_ids:
            continue
        items.append(_normalize(spec))
        added += 1

    status_counts: dict[str, int] = {}
    for it in items:
        status = str(it.get("status") or "NOT_DONE")
        status_counts[status] = status_counts.get(status, 0) + 1

    register["items"] = items
    register["item_count"] = len(items)
    register["status_counts"] = status_counts
    register["generated_at"] = datetime.now(timezone.utc).isoformat()

    REGISTER_PATH.write_text(json.dumps(register, indent=2) + "\n", encoding="utf-8")
    LOGGER.info("register extended: +%d items (total %d)", added, len(items))
    LOGGER.info("status counts: %s", status_counts)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
