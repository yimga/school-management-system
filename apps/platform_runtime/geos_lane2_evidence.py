"""GEOS-99 Lane 2 evidence helpers (register sync + JSON validation)."""

from __future__ import annotations

import json
import re
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent.parent

EVIDENCE_ROOT = ROOT / "var" / "evidence" / "geos-99"

PLACEHOLDER_MARKERS = ("YYYY-MM-DD", "<", "pi_…", "ch_…", "pending_operator", "pending")

LIVE_SATISFIED_STATUSES = frozenset({"verified_live", "not_required"})

PILLAR_LIVE_ENTRY_IDS: dict[str, tuple[str, ...]] = {
    "shopify": (
        "manual_fallback_operations",
        "sfdp_lane2_pilot_corridors",
    ),
    "google": ("openai_litellm_option_a",),
    "aws": ("cloud_dns_placeholder", "hosting_render_sha_parity"),
    "linux": ("mobile_distribution_placeholder", "sovereign_offline_delivery_platform"),
    "localglobal": ("data_localization_placeholder",),
}

PILOT_GEOS_GATE_SLOTS = frozenset({1})


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def evidence_path_from_notes(notes: str) -> Path | None:
    if not notes:
        return None
    match = re.search(r"(var/evidence/geos-99/[^\s;]+)", notes)
    if not match:
        return None
    rel = match.group(1).replace("\\", "/")
    return ROOT / Path(rel)


def evidence_json_complete(path: Path) -> bool:
    if not path.is_file():
        return False
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return False
    status = str(data.get("evidence_status") or data.get("status") or "").lower()
    if status in {"pending_operator", "pending", "not_started"}:
        return False
    if status in {"verified_live", "complete", "repo_complete"}:
        return True
    if data.get("repo_complete") is True:
        return True
    blob = json.dumps(data)
    if any(marker in blob for marker in PLACEHOLDER_MARKERS):
        return False
    return True


def entry_live_satisfied(entry: dict[str, Any]) -> bool:
    status = str(entry.get("status") or "not_started")
    if status in LIVE_SATISFIED_STATUSES:
        return True
    if status in {"repo_complete", "approved_production", "approved_test"}:
        notes = str(entry.get("evidence_notes") or "")
        path = evidence_path_from_notes(notes)
        if path and evidence_json_complete(path):
            return True
        if status == "repo_complete" and path and path.is_file():
            return True
    return False


def load_register() -> dict[str, Any]:
    path = ROOT / "docs" / "external_dependencies_register.json"
    return json.loads(path.read_text(encoding="utf-8"))


def save_register(data: dict[str, Any]) -> None:
    path = ROOT / "docs" / "external_dependencies_register.json"
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def iter_register_entries(data: dict[str, Any]):
    for section in data.get("sections") or []:
        for entry in section.get("entries") or []:
            yield section, entry


def live_pct_from_entry_ids(entry_ids: tuple[str, ...]) -> float:
    if not entry_ids:
        return 0.0
    data = load_register()
    matched: list[dict[str, Any]] = []
    for _section, entry in iter_register_entries(data):
        if entry.get("id") in entry_ids:
            matched.append(entry)
    if not matched:
        return 0.0
    satisfied = sum(1 for entry in matched if entry_live_satisfied(entry))
    return round(100.0 * satisfied / len(matched), 1)


def pilot_slot_pct(slots: frozenset[int] | None = None) -> float:
    gate = slots or PILOT_GEOS_GATE_SLOTS
    path = ROOT / "docs" / "generated" / "pilot_readiness_scorecard.json"
    if not path.is_file():
        return 0.0
    data = json.loads(path.read_text(encoding="utf-8"))
    pilots = data.get("pilots") or data.get("slots") or []
    if not pilots:
        return 0.0
    core_keys = (
        "attendance_completed",
        "marks_completed",
        "report_generated",
        "invoice_created",
        "receipt_or_payment_captured",
        "parent_portal_viewed",
    )

    def slot_done(pilot: dict[str, Any]) -> bool:
        if not all(pilot.get(k) for k in core_keys):
            return False
        if pilot.get("offline_sync_required") and not pilot.get("offline_sync_used"):
            return False
        return True

    gated = [p for p in pilots if int(p.get("slot") or 0) in gate]
    if not gated:
        return 0.0
    done = sum(1 for p in gated if slot_done(p))
    return round(100.0 * done / len(gated), 1)


def flip_register_entry(
    entry_id: str,
    *,
    status: str,
    evidence_notes: str | None = None,
) -> bool:
    data = load_register()
    changed = False
    for _section, entry in iter_register_entries(data):
        if entry.get("id") != entry_id:
            continue
        if entry.get("status") != status:
            entry["status"] = status
            changed = True
        if evidence_notes is not None and entry.get("evidence_notes") != evidence_notes:
            entry["evidence_notes"] = evidence_notes
            changed = True
    if changed:
        save_register(data)
    return changed
