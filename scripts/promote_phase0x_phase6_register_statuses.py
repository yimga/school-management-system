#!/usr/bin/env python3
"""Promote Phase 0X items to DONE and Phase 6 items to IN_PROGRESS once their
companion verifiers are green.

Honest semantics:
  - Phase 0X verifiers gate documents / shards / runbooks that DO exist now -> DONE.
  - Phase 6 turbo verifiers are scaffold-presence only; runtime implementation is
    still missing. They move from NOT_DONE -> IN_PROGRESS so the program does not
    falsely claim closure.
"""

from __future__ import annotations

import json
import logging
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

LOGGER = logging.getLogger("promote_register_statuses")

REPO = Path(__file__).resolve().parents[1]
REGISTER_PATH = REPO / "docs" / "generated" / "global_governance_completion_register.json"


PHASE_0X_TO_VERIFIER: dict[str, str] = {
    "P0X-regulatory-matrices": "scripts/verify_regulatory_matrix_coverage.py",
    "P0X-edge-jurisdictions": "scripts/verify_edge_jurisdiction_coverage.py",
    "P0X-data-lineage-versioning": "scripts/verify_matrix_provenance.py",
    "P0X-org-lifecycle-events": "scripts/verify_org_lifecycle_events.py",
    "P0X-exam-boards-matrix": "scripts/verify_exam_board_coverage.py",
    "P0X-legacy-mis-map": "scripts/verify_legacy_mis_route_coverage.py",
    "P0X-national-identity-sso": "scripts/verify_national_sso_brokers.py",
    "P0X-calendars-holidays-religious": "scripts/verify_calendar_ingestion.py",
    "P0X-labor-law-matrix": "scripts/verify_labor_law_matrix.py",
    "P0X-minority-language-rights": "scripts/verify_minority_language_rights.py",
    "P0X-accessibility-statutes": "scripts/verify_accessibility_matrix.py",
    "P0X-dr-rto-rpo-residency": "scripts/verify_dr_rto_rpo_residency.py",
    "P0X-pricing-ppp-fx": "scripts/verify_pricing_ppp_matrix.py",
    "P0X-risk-register-quantified": "scripts/verify_risk_register.py",
    "P0X-rollback-criteria-per-phase": "scripts/verify_rollback_runbooks.py",
    "P0X-customer-comms-migration": "scripts/verify_customer_comms_templates.py",
    "P0X-telemetry-slo-per-phase": "scripts/verify_phase_slo_budgets.py",
    "P0X-property-tests-governance": "scripts/verify_governance_property_tests.py",
}


PHASE_6_TO_VERIFIER: dict[str, str] = {
    "P6-agentic-self-healing-matrix": "scripts/verify_matrix_freshness.py",
    "P6-formal-verification-tla": "scripts/verify_tla_specs.py",
    "P6-realtime-compliance-engine": "scripts/verify_compliance_engine.py",
    "P6-sovereignty-trust-score": "scripts/verify_sovereignty_trust_score.py",
    "P6-cross-vertical-kernel": "scripts/verify_cross_vertical_kernel.py",
    "P6-multimodal-terminology": "scripts/verify_multimodal_terminology.py",
    "P6-regulator-api-federation": "scripts/verify_regulator_api_federation.py",
    "P6-adversarial-redteam": "scripts/verify_adversarial_redteam.py",
    "P6-w3c-verifiable-credentials": "scripts/verify_w3c_verifiable_credentials.py",
    "P6-time-traveling-matrix": "scripts/verify_time_traveling_matrix.py",
    "P6-zero-form-bootstrap": "scripts/verify_zero_form_bootstrap.py",
    "P6-ai-policy-copilot": "scripts/verify_ai_policy_copilot.py",
    "P6-cross-org-marketplace": "scripts/verify_cross_org_marketplace.py",
    "P6-federated-emis-aggregator": "scripts/verify_federated_emis_aggregator.py",
    "P6-living-competitor-tracker": "scripts/verify_competitor_tracker.py",
}


def _run_verifier(rel_path: str) -> bool:
    full = REPO / rel_path
    if not full.is_file():
        return False
    result = subprocess.run(
        [sys.executable, str(full)],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode == 0


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    if not REGISTER_PATH.is_file():
        LOGGER.error("register missing")
        return 1
    register = json.loads(REGISTER_PATH.read_text(encoding="utf-8"))
    items = register.get("items") or []

    promotions = 0
    for item in items:
        item_id = str(item.get("id") or "")
        if item_id in PHASE_0X_TO_VERIFIER:
            verifier_path = PHASE_0X_TO_VERIFIER[item_id]
            if _run_verifier(verifier_path) and item.get("status") != "DONE":
                item["status"] = "DONE"
                promotions += 1
        elif item_id in PHASE_6_TO_VERIFIER:
            verifier_path = PHASE_6_TO_VERIFIER[item_id]
            if _run_verifier(verifier_path) and item.get("status") == "NOT_DONE":
                item["status"] = "IN_PROGRESS"
                promotions += 1

    status_counts: dict[str, int] = {}
    for item in items:
        status = str(item.get("status") or "NOT_DONE")
        status_counts[status] = status_counts.get(status, 0) + 1
    register["items"] = items
    register["status_counts"] = status_counts
    register["generated_at"] = datetime.now(timezone.utc).isoformat()
    REGISTER_PATH.write_text(json.dumps(register, indent=2) + "\n", encoding="utf-8")
    LOGGER.info("promotions applied: %d", promotions)
    LOGGER.info("status counts: %s", status_counts)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
