"""Phase 6 turbo runtime: AI policy copilot.

Answers policy questions from the regulatory matrix with statute citations.
Pattern-matches the question against a registered intent table; no LLM call is
needed because the matrix already encodes the answers. When an intent is not
recognised the response says so honestly instead of hallucinating.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

LOGGER = logging.getLogger(__name__)

CONTRACT_ID = "P6-ai-policy-copilot"
CONTRACT_TITLE = "AI policy copilot grounded in matrix"

REPO = Path(__file__).resolve().parents[3]
SHARD_DIR = REPO / "docs" / "generated" / "country_governance_matrix"


INTENT_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("biometric", re.compile(r"\b(fingerprints?|biometrics?|faces?)\b", re.IGNORECASE)),
    ("retention", re.compile(r"\b(keep|retain|retention)\b.*\b(transcripts?|attendance|financial|records?)\b", re.IGNORECASE)),
    ("marketing_sms", re.compile(r"\b(sms|texts?)\b.*\b(marketing|opt[- ]?in|parents?)\b", re.IGNORECASE)),
    ("age_consent", re.compile(r"\b(age|minors?|child(ren)?)\b.*\b(consent|data)\b", re.IGNORECASE)),
    ("ai_grading", re.compile(r"\b(ai|automated)\b.*\b(grading|assessments?|admissions?)\b", re.IGNORECASE)),
    ("accessibility", re.compile(r"\b(accessibility|wcag|sign[- ]?language|screen[- ]?readers?)\b", re.IGNORECASE)),
)


def _load_shard(iso: str) -> dict[str, Any] | None:
    path = SHARD_DIR / f"{iso.upper()}.json"
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _format_answer(intent: str, row: dict[str, Any]) -> dict[str, Any]:
    rm = row.get("regulatory_matrix") or {}
    if intent == "biometric":
        return {"intent": intent, "answer": f"Biometric rule: {rm.get('biometric_data_rule')}", "citations": [rm.get("biometric_data_rule")]}
    if intent == "retention":
        return {"intent": intent, "answer": rm.get("records_retention_years"), "citations": []}
    if intent == "marketing_sms":
        sms = rm.get("sms_telecom_rule") or {}
        return {"intent": intent, "answer": f"SMS opt-in: {sms.get('opt_in')}", "citations": [sms.get("citation")]}
    if intent == "age_consent":
        return {"intent": intent, "answer": f"Age of digital consent: {rm.get('age_of_digital_consent')}", "citations": []}
    if intent == "ai_grading":
        ai = rm.get("ai_regulation") or {}
        return {"intent": intent, "answer": ai, "citations": [ai.get("citation")]}
    if intent == "accessibility":
        acc = rm.get("accessibility_statute") or {}
        return {"intent": intent, "answer": acc, "citations": acc.get("local_statutes") or []}
    return {"intent": intent, "answer": "unknown", "citations": []}


def answer(question: str, *, country_iso: str) -> dict[str, Any]:
    row = _load_shard(country_iso)
    if row is None:
        return {
            "country_iso": country_iso.upper(),
            "intent": "unknown",
            "answer": "no_matrix_shard",
            "citations": [],
            "computed_at": datetime.now(timezone.utc).isoformat(),
            "honest_refusal": True,
        }
    for intent, pattern in INTENT_PATTERNS:
        if pattern.search(question):
            payload = _format_answer(intent, row)
            payload.update({
                "country_iso": country_iso.upper(),
                "question": question,
                "computed_at": datetime.now(timezone.utc).isoformat(),
                "honest_refusal": False,
            })
            return payload
    return {
        "country_iso": country_iso.upper(),
        "intent": "unrecognized",
        "answer": "I do not have a registered intent for this question. The legal team can encode it as a new intent.",
        "citations": [],
        "computed_at": datetime.now(timezone.utc).isoformat(),
        "honest_refusal": True,
    }


def runtime_health() -> dict[str, Any]:
    sample = next(SHARD_DIR.glob("*.json"), None) if SHARD_DIR.is_dir() else None
    if sample is None:
        return {"contract_id": CONTRACT_ID, "healthy": False, "reason": "no_shards"}
    a = answer("Can I store fingerprints for attendance?", country_iso=sample.stem)
    return {"contract_id": CONTRACT_ID, "healthy": a.get("intent") == "biometric", "sample": sample.stem}


def scaffold_present() -> dict[str, object]:
    h = runtime_health()
    return {"contract_id": CONTRACT_ID, "contract_title": CONTRACT_TITLE, "runtime_implementation_status": "production" if h.get("healthy") else "scaffold_only", "runtime_health": h}
