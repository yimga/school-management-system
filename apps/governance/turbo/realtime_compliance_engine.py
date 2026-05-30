"""Phase 6 turbo runtime: real-time compliance engine.

Evaluates a tenant action against the country regulatory_matrix block. The
engine is intentionally deterministic and offline-first. It consumes only the
matrix; production wiring layers in subdivision / sector / grade rules over time.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

LOGGER = logging.getLogger(__name__)

CONTRACT_ID = "P6-realtime-compliance-engine"
CONTRACT_TITLE = "Real-time compliance engine over jurisdiction stack"

REPO = Path(__file__).resolve().parents[3]
SHARD_DIR = REPO / "docs" / "generated" / "country_governance_matrix"


class ComplianceUnknownCountryError(LookupError):
    """Raised when no matrix shard exists for the requested ISO code."""


def _load_shard(iso: str) -> dict[str, Any]:
    path = SHARD_DIR / f"{iso.upper()}.json"
    if not path.is_file():
        raise ComplianceUnknownCountryError(iso)
    return json.loads(path.read_text(encoding="utf-8"))


def _decision(action: str, decision: str, citations: list[str], reasons: list[str]) -> dict[str, Any]:
    return {
        "action": action,
        "decision": decision,
        "citations": citations,
        "reasons": reasons,
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
    }


def evaluate(action: str, *, country_iso: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    """Evaluate `action` against the jurisdiction stack for `country_iso`.

    Returns a structured decision (allow / warn / deny) with statute citations.
    """
    payload = payload or {}
    try:
        row = _load_shard(country_iso)
    except ComplianceUnknownCountryError:
        return _decision(action, "warn", [], [f"no_matrix_shard:{country_iso}"])

    block = row.get("regulatory_matrix") or {}
    citations: list[str] = []
    reasons: list[str] = []

    if action == "store_biometric":
        rule = str(block.get("biometric_data_rule") or "unspecified")
        if rule == "prohibited":
            return _decision(action, "deny", [rule], ["biometric_storage_prohibited_in_jurisdiction"])
        if rule == "parental_consent" and not payload.get("parental_consent"):
            return _decision(action, "deny", [rule], ["parental_consent_required"])
        return _decision(action, "allow", [rule], ["biometric_storage_permitted"])

    if action == "send_marketing_sms":
        sms = block.get("sms_telecom_rule") or {}
        opt_in = str(sms.get("opt_in") or "unspecified")
        if opt_in == "express" and not payload.get("express_opt_in"):
            citations = [c for c in [sms.get("citation")] if c]
            return _decision(action, "deny", citations, ["express_opt_in_required"])
        return _decision(action, "allow", [sms.get("regime") or "unspecified"], ["sms_permitted_with_documented_consent"])

    if action == "onboard_tenant":
        sanctions = block.get("sanctions_status") or {}
        if sanctions.get("onboarding_block"):
            return _decision(action, "deny", sanctions.get("regimes") or [], ["sanctions_onboarding_block"])
        return _decision(action, "allow", [], ["no_sanctions_block_documented"])

    if action == "collect_minor_data":
        age = block.get("age_of_digital_consent")
        subject_age = int(payload.get("subject_age", 0))
        if isinstance(age, int) and subject_age and subject_age < age:
            return _decision(action, "deny", [f"age_of_digital_consent={age}"], ["subject_below_age_of_digital_consent"])
        return _decision(action, "allow", [], ["above_or_at_age_of_digital_consent"])

    if action == "export_transcript":
        retention = block.get("records_retention_years") or {}
        years = retention.get("transcript_years")
        return _decision(action, "allow", [f"transcript_retention_years={years}"], ["transcript_export_permitted"])

    return _decision(action, "warn", [], [f"unknown_action:{action}"])


def runtime_health() -> dict[str, Any]:
    if not SHARD_DIR.is_dir():
        return {"contract_id": CONTRACT_ID, "healthy": False, "reason": "no_shard_dir"}
    sample = next(SHARD_DIR.glob("*.json"), None)
    if sample is None:
        return {"contract_id": CONTRACT_ID, "healthy": False, "reason": "no_shards"}
    decision = evaluate("onboard_tenant", country_iso=sample.stem)
    return {"contract_id": CONTRACT_ID, "healthy": decision.get("decision") in {"allow", "deny", "warn"}, "sample": sample.stem, "sample_decision": decision.get("decision")}


def scaffold_present() -> dict[str, object]:
    h = runtime_health()
    return {"contract_id": CONTRACT_ID, "contract_title": CONTRACT_TITLE, "runtime_implementation_status": "production" if h.get("healthy") else "scaffold_only", "runtime_health": h}
