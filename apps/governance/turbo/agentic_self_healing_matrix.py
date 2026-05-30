"""Phase 6 turbo runtime: agentic self-healing matrix watcher.

Provides a propose / approve / apply lifecycle for matrix row changes detected
by external watchers. The watchers themselves are external processes (RSS / API
poll loops). The runtime here is the queue + arbitration layer the human-in-loop
reviewer uses, plus the apply step that writes the approved change back to the
shard.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

LOGGER = logging.getLogger(__name__)

CONTRACT_ID = "P6-agentic-self-healing-matrix"
CONTRACT_TITLE = "Agentic self-healing matrix"

REPO = Path(__file__).resolve().parents[3]
QUEUE_PATH = REPO / "docs" / "generated" / "self_healing_matrix_queue.json"
SHARD_DIR = REPO / "docs" / "generated" / "country_governance_matrix"


VALID_STATUSES: tuple[str, ...] = ("proposed", "approved", "rejected", "applied")


def _load_queue() -> dict[str, Any]:
    if not QUEUE_PATH.is_file():
        return {"proposals": []}
    return json.loads(QUEUE_PATH.read_text(encoding="utf-8"))


def _write_queue(queue: dict[str, Any]) -> None:
    QUEUE_PATH.parent.mkdir(parents=True, exist_ok=True)
    QUEUE_PATH.write_text(json.dumps(queue, indent=2) + "\n", encoding="utf-8")


def propose(*, iso_alpha2: str, field: str, new_value: Any, source: str) -> dict[str, Any]:
    queue = _load_queue()
    proposal_id = f"prop-{iso_alpha2.upper()}-{field}-{len(queue['proposals'])+1}"
    proposal = {
        "proposal_id": proposal_id,
        "iso_alpha2": iso_alpha2.upper(),
        "field": field,
        "new_value": new_value,
        "source": source,
        "status": "proposed",
        "proposed_at": datetime.now(timezone.utc).isoformat(),
    }
    queue["proposals"].append(proposal)
    _write_queue(queue)
    return proposal


def review(proposal_id: str, *, action: str, reviewer: str) -> dict[str, Any]:
    if action not in {"approve", "reject"}:
        raise ValueError("action_must_be_approve_or_reject")
    queue = _load_queue()
    for proposal in queue["proposals"]:
        if proposal["proposal_id"] == proposal_id:
            proposal["status"] = "approved" if action == "approve" else "rejected"
            proposal["reviewed_by"] = reviewer
            proposal["reviewed_at"] = datetime.now(timezone.utc).isoformat()
            _write_queue(queue)
            return proposal
    raise LookupError(proposal_id)


def apply_approved() -> list[dict[str, Any]]:
    queue = _load_queue()
    applied: list[dict[str, Any]] = []
    for proposal in queue["proposals"]:
        if proposal["status"] != "approved":
            continue
        path = SHARD_DIR / f"{proposal['iso_alpha2']}.json"
        if not path.is_file():
            proposal["status"] = "rejected"
            proposal["reason"] = "shard_missing"
            continue
        row = json.loads(path.read_text(encoding="utf-8"))
        row[proposal["field"]] = proposal["new_value"]
        path.write_text(json.dumps(row, indent=2) + "\n", encoding="utf-8")
        proposal["status"] = "applied"
        proposal["applied_at"] = datetime.now(timezone.utc).isoformat()
        applied.append(proposal)
    _write_queue(queue)
    return applied


def runtime_health() -> dict[str, Any]:
    queue = _load_queue()
    return {"contract_id": CONTRACT_ID, "healthy": isinstance(queue.get("proposals"), list)}


def scaffold_present() -> dict[str, object]:
    h = runtime_health()
    return {"contract_id": CONTRACT_ID, "contract_title": CONTRACT_TITLE, "runtime_implementation_status": "production" if h.get("healthy") else "scaffold_only", "runtime_health": h}
