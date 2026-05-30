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

    # ---- v4.00.91 Studio-OS-10X W1 Pillar C13 — 5 new actions --------------
    if action == "export_transcript_to_country":
        target_iso = str(payload.get("target_country_iso") or "").upper()
        sanctions = block.get("sanctions_status") or {}
        if sanctions.get("onboarding_block"):
            return _decision(action, "deny", sanctions.get("regimes") or [],
                             [f"source_country_sanctioned:{country_iso}"])
        if target_iso and target_iso != country_iso.upper():
            try:
                target_row = _load_shard(target_iso)
            except ComplianceUnknownCountryError:
                return _decision(action, "warn", [], [f"no_target_matrix:{target_iso}"])
            target_sanctions = (target_row.get("regulatory_matrix") or {}).get("sanctions_status") or {}
            if target_sanctions.get("onboarding_block"):
                return _decision(action, "deny", target_sanctions.get("regimes") or [],
                                 [f"target_country_sanctioned:{target_iso}"])
        return _decision(action, "allow", [], ["cross_border_transcript_export_permitted"])

    if action == "enroll_minor":
        age = block.get("age_of_digital_consent")
        subject_age = int(payload.get("subject_age", 0))
        parental_consent = bool(payload.get("parental_consent"))
        if isinstance(age, int) and subject_age and subject_age < age and not parental_consent:
            return _decision(action, "deny", [f"age_of_digital_consent={age}"],
                             ["enrollment_below_age_requires_parental_consent"])
        return _decision(action, "allow", [], ["enrollment_age_or_parental_consent_satisfied"])

    if action == "share_iep_with_vendor":
        vendor_dpa_signed = bool(payload.get("vendor_dpa_signed"))
        vendor_subprocessor_listed = bool(payload.get("vendor_subprocessor_listed"))
        privacy = list(block.get("student_privacy_regimes") or [])
        if not vendor_dpa_signed:
            return _decision(action, "deny", privacy, ["iep_share_blocked_no_dpa"])
        if not vendor_subprocessor_listed:
            return _decision(action, "warn", privacy, ["iep_share_vendor_not_in_subprocessor_list"])
        return _decision(action, "allow", privacy, ["iep_share_permitted_with_dpa_and_listing"])

    if action == "proctor_with_camera_only":
        rule = str(block.get("biometric_data_rule") or "unspecified")
        if rule == "prohibited":
            return _decision(action, "deny", [rule], ["proctoring_camera_treated_as_biometric_prohibited"])
        if rule == "parental_consent" and not payload.get("parental_consent"):
            return _decision(action, "warn", [rule], ["proctoring_camera_warn_parental_consent_recommended"])
        return _decision(action, "allow", [rule], ["proctoring_camera_permitted"])

    if action == "archive_finance_records":
        retention = block.get("records_retention_years") or {}
        years = retention.get("financial_years")
        requested_years = int(payload.get("retention_years_requested", 0))
        if isinstance(years, int) and requested_years and requested_years < years:
            return _decision(action, "deny", [f"financial_retention_years={years}"],
                             [f"requested_{requested_years}_below_statute_{years}"])
        return _decision(action, "allow", [f"financial_retention_years={years}"], ["finance_archive_permitted"])
    # ---- end v4.00.91 --------------------------------------------------------

    return _decision(action, "warn", [], [f"unknown_action:{action}"])


# Public surface — frozen tuple of supported actions for verifier + UI dropdown.
SUPPORTED_ACTIONS = (
    "store_biometric",
    "send_marketing_sms",
    "onboard_tenant",
    "collect_minor_data",
    "export_transcript",
    "export_transcript_to_country",
    "enroll_minor",
    "share_iep_with_vendor",
    "proctor_with_camera_only",
    "archive_finance_records",
)


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
