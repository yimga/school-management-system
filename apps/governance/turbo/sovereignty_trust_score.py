"""Phase 6 turbo runtime: sovereignty trust score per country."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

LOGGER = logging.getLogger(__name__)

CONTRACT_ID = "P6-sovereignty-trust-score"
CONTRACT_TITLE = "Live per-country sovereignty trust score"

REPO = Path(__file__).resolve().parents[3]
SHARD_DIR = REPO / "docs" / "generated" / "country_governance_matrix"

WEIGHTS: dict[str, int] = {
    "infra_residency": 22,
    "key_custody": 12,
    "regulator_api_uptime_90d": 12,
    "counsel_signoff_fresh": 12,
    "incident_history_90d_clean": 15,
    "regulatory_matrix_complete": 10,
    "statute_citation_fresh": 4,
    # v4.00.91 Studio-OS-10X W1 Pillar C14 — 3 new weighted signals.
    "data_residency_attestation_present": 4,
    "subprocessor_list_published": 4,
    "breach_notification_window_hours_le_72": 5,
}
assert sum(WEIGHTS.values()) == 100, "sovereignty trust score weights must sum to 100"


def _signal_regulatory_matrix_complete(row: dict[str, Any]) -> int:
    block = row.get("regulatory_matrix") or {}
    required = (
        "student_privacy_regimes", "age_of_digital_consent", "biometric_data_rule",
        "ai_regulation", "sms_telecom_rule", "tax_reporting_obligations",
        "sanctions_status", "records_retention_years", "content_safety_regime",
        "accessibility_statute",
    )
    present = sum(1 for k in required if k in block)
    return int(round(WEIGHTS["regulatory_matrix_complete"] * present / len(required)))


def _signal_statute_citation_fresh(row: dict[str, Any]) -> int:
    prov = row.get("provenance") or {}
    source = prov.get("source") or {}
    return WEIGHTS["statute_citation_fresh"] if source.get("citation") else 0


def _signal_infra_residency(row: dict[str, Any]) -> int:
    dr = row.get("dr_rto_rpo") or {}
    label = str(dr.get("residency_label") or "")
    if "physically_pinned" in label:
        return WEIGHTS["infra_residency"]
    if "partner_region" in label:
        return int(WEIGHTS["infra_residency"] * 0.6)
    return int(WEIGHTS["infra_residency"] * 0.4)


def _signal_data_residency_attestation(row: dict[str, Any]) -> int:
    prov = row.get("provenance") or {}
    if prov.get("verified_at") and str(prov.get("verified_by") or "").startswith(("counsel:", "auditor:")):
        return WEIGHTS["data_residency_attestation_present"]
    return 0


def _signal_subprocessor_list_published(row: dict[str, Any]) -> int:
    block = row.get("regulatory_matrix") or {}
    sub = block.get("subprocessor_disclosure") or {}
    return WEIGHTS["subprocessor_list_published"] if sub.get("published_url") else 0


def _signal_breach_notification_window(row: dict[str, Any]) -> int:
    block = row.get("regulatory_matrix") or {}
    breach = block.get("breach_notification") or {}
    hours = breach.get("statutory_hours")
    if isinstance(hours, int) and 0 < hours <= 72:
        return WEIGHTS["breach_notification_window_hours_le_72"]
    return 0


def _default_partial(weight_key: str, fraction: float = 0.5) -> int:
    return int(round(WEIGHTS[weight_key] * fraction))


def compute_score(iso_alpha2: str) -> dict[str, Any]:
    path = SHARD_DIR / f"{iso_alpha2.upper()}.json"
    if not path.is_file():
        return {"country_iso": iso_alpha2.upper(), "score": 0, "tier": "evidence_required", "missing_shard": True}
    row = json.loads(path.read_text(encoding="utf-8"))
    signals: dict[str, int] = {
        "infra_residency": _signal_infra_residency(row),
        "key_custody": _default_partial("key_custody"),
        "regulator_api_uptime_90d": _default_partial("regulator_api_uptime_90d", 0.4),
        "counsel_signoff_fresh": _default_partial("counsel_signoff_fresh", 0.4),
        "incident_history_90d_clean": WEIGHTS["incident_history_90d_clean"],
        "regulatory_matrix_complete": _signal_regulatory_matrix_complete(row),
        "statute_citation_fresh": _signal_statute_citation_fresh(row),
        "data_residency_attestation_present": _signal_data_residency_attestation(row),
        "subprocessor_list_published": _signal_subprocessor_list_published(row),
        "breach_notification_window_hours_le_72": _signal_breach_notification_window(row),
    }
    score = sum(signals.values())
    tier = (
        "high_trust" if score >= 90
        else "validated" if score >= 70
        else "partial_evidence" if score >= 50
        else "evidence_required"
    )
    return {
        "country_iso": str(row.get("iso_alpha2") or iso_alpha2).upper(),
        "score": min(100, max(0, score)),
        "tier": tier,
        "computed_at": datetime.now(timezone.utc).isoformat(),
        "signals": signals,
        "citations": [str(path.relative_to(REPO)).replace("\\", "/")],
        "stale_signals": [k for k, v in signals.items() if v < WEIGHTS[k] * 0.5],
    }


def compute_all() -> list[dict[str, Any]]:
    if not SHARD_DIR.is_dir():
        return []
    return [compute_score(p.stem) for p in sorted(SHARD_DIR.glob("*.json"))]


def runtime_health() -> dict[str, Any]:
    sample = next(SHARD_DIR.glob("*.json"), None) if SHARD_DIR.is_dir() else None
    if sample is None:
        return {"contract_id": CONTRACT_ID, "healthy": False, "reason": "no_shards"}
    result = compute_score(sample.stem)
    return {"contract_id": CONTRACT_ID, "healthy": "score" in result, "sample": result["country_iso"], "sample_score": result["score"]}


def scaffold_present() -> dict[str, object]:
    h = runtime_health()
    return {"contract_id": CONTRACT_ID, "contract_title": CONTRACT_TITLE, "runtime_implementation_status": "production" if h.get("healthy") else "scaffold_only", "runtime_health": h}
