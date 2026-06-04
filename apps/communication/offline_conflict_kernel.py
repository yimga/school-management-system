"""Wave S-E (v3.96.1 — 2026-05-26) — Offline-sync conflict resolution kernel.

When a teacher works offline (PWA queue) and writes are replayed against a
server that may have changed in the interim, conflicts happen. This kernel
resolves them under a per-record-type policy so the sync layer doesn't ship
"last writer wins" silently — which is how grade rows quietly disappear.

Per record type policy:

- ``attendance`` — LATER_WINS by timestamp (last roll-call mark stands).
- ``grade`` — MANUAL_REVIEW required (grades are too sensitive for auto-merge).
- ``profile`` — MERGE_FIELDS (combine non-conflicting field updates; flag
  truly conflicting field overlaps for manual review).
- ``message`` — LATER_WINS by timestamp.
- ``homework_submission`` — REMOTE_WINS once server has accepted a row
  (offline duplicates dropped).

The kernel produces a ``ConflictResolution`` dataclass with the winning row,
the loser, and a ``manual_review_required`` flag the sync queue uses to
park the row for the operator.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


# --- Strategy enum --------------------------------------------------------

LATER_WINS = "LATER_WINS"
REMOTE_WINS = "REMOTE_WINS"
LOCAL_WINS = "LOCAL_WINS"
MERGE_FIELDS = "MERGE_FIELDS"
MANUAL_REVIEW = "MANUAL_REVIEW"

ALL_STRATEGIES = (LATER_WINS, REMOTE_WINS, LOCAL_WINS, MERGE_FIELDS, MANUAL_REVIEW)


_DEFAULT_POLICY: dict[str, str] = {
    "attendance": LATER_WINS,
    "grade": MANUAL_REVIEW,
    "profile": MERGE_FIELDS,
    "message": LATER_WINS,
    "homework_submission": REMOTE_WINS,
    "behavior_event": LATER_WINS,
    "fee_payment": MANUAL_REVIEW,
}


def get_default_strategy(record_type: str) -> str:
    return _DEFAULT_POLICY.get(record_type, MANUAL_REVIEW)


# --- Record shape ---------------------------------------------------------


@dataclass(frozen=True)
class SyncRecord:
    """One offline-queued or server-side record being reconciled."""

    record_type: str
    record_key: str  # stable id (or composite "studentid:date" for attendance)
    payload: dict[str, Any]
    timestamp_iso: str
    source: str  # "local" | "remote"


# --- Resolution result ----------------------------------------------------


@dataclass
class ConflictResolution:
    record_type: str
    record_key: str
    strategy: str
    winner_source: str = ""  # "local" | "remote" | "merged" | ""
    winner_payload: dict[str, Any] = field(default_factory=dict)
    loser_payload: dict[str, Any] = field(default_factory=dict)
    manual_review_required: bool = False
    diff_fields: list[str] = field(default_factory=list)
    notes: str = ""

    def as_dict(self) -> dict:
        return {
            "record_type": self.record_type,
            "record_key": self.record_key,
            "strategy": self.strategy,
            "winner_source": self.winner_source,
            "winner_payload": dict(self.winner_payload),
            "loser_payload": dict(self.loser_payload),
            "manual_review_required": self.manual_review_required,
            "diff_fields": list(self.diff_fields),
            "notes": self.notes,
        }


# --- Helpers --------------------------------------------------------------


def _parse_ts(s: str) -> datetime | None:
    try:
        return datetime.fromisoformat(s)
    except (ValueError, TypeError):
        return None


def _diff_fields(a: dict, b: dict) -> list[str]:
    keys = set(a.keys()) | set(b.keys())
    return sorted(k for k in keys if a.get(k) != b.get(k))


def _merge_non_conflicting_fields(
    local: dict, remote: dict,
) -> tuple[dict, list[str]]:
    """Merge fields that don't disagree. Return ``(merged, conflict_fields)``."""
    merged: dict[str, Any] = {}
    conflict_fields: list[str] = []
    keys = set(local.keys()) | set(remote.keys())
    for k in keys:
        in_local = k in local
        in_remote = k in remote
        if in_local and in_remote:
            if local[k] == remote[k]:
                merged[k] = local[k]
            else:
                # True conflict — surface for manual review.
                conflict_fields.append(k)
                # Default the merged value to remote; reviewer can override.
                merged[k] = remote[k]
        elif in_local:
            merged[k] = local[k]
        else:
            merged[k] = remote[k]
    return merged, conflict_fields


# --- Core resolution ------------------------------------------------------


def resolve_conflict(
    *,
    local: SyncRecord,
    remote: SyncRecord,
    strategy: str | None = None,
) -> ConflictResolution:
    if local.record_type != remote.record_type:
        raise ValueError(
            f"record_type_mismatch:{local.record_type}_vs_{remote.record_type}"
        )
    if local.record_key != remote.record_key:
        raise ValueError("record_key_mismatch")

    chosen_strategy = strategy or get_default_strategy(local.record_type)
    if chosen_strategy not in ALL_STRATEGIES:
        raise ValueError(f"unknown_strategy:{chosen_strategy}")

    result = ConflictResolution(
        record_type=local.record_type,
        record_key=local.record_key,
        strategy=chosen_strategy,
        diff_fields=_diff_fields(local.payload, remote.payload),
    )

    # Short-circuit: no actual conflict if payloads are identical.
    if not result.diff_fields:
        result.winner_source = "remote"
        result.winner_payload = dict(remote.payload)
        result.loser_payload = dict(local.payload)
        result.notes = "no_diff"
        return result

    if chosen_strategy == LATER_WINS:
        l_ts = _parse_ts(local.timestamp_iso)
        r_ts = _parse_ts(remote.timestamp_iso)
        if l_ts is None and r_ts is None:
            result.manual_review_required = True
            result.notes = "both_timestamps_unparseable"
            result.winner_payload = dict(remote.payload)
            result.loser_payload = dict(local.payload)
            return result
        if l_ts is None:
            winner, loser = remote, local
        elif r_ts is None:
            winner, loser = local, remote
        elif l_ts > r_ts:
            winner, loser = local, remote
        elif r_ts > l_ts:
            winner, loser = remote, local
        else:
            # Exact-tie timestamp — prefer remote (server is authoritative
            # under tie) but mark for review so the operator can audit.
            result.manual_review_required = True
            result.notes = "tied_timestamps"
            result.winner_payload = dict(remote.payload)
            result.loser_payload = dict(local.payload)
            result.winner_source = "remote"
            return result
        result.winner_source = winner.source
        result.winner_payload = dict(winner.payload)
        result.loser_payload = dict(loser.payload)
        return result

    if chosen_strategy == REMOTE_WINS:
        result.winner_source = "remote"
        result.winner_payload = dict(remote.payload)
        result.loser_payload = dict(local.payload)
        return result

    if chosen_strategy == LOCAL_WINS:
        result.winner_source = "local"
        result.winner_payload = dict(local.payload)
        result.loser_payload = dict(remote.payload)
        return result

    if chosen_strategy == MERGE_FIELDS:
        merged, conflict_fields = _merge_non_conflicting_fields(
            local.payload, remote.payload,
        )
        result.winner_source = "merged"
        result.winner_payload = merged
        result.loser_payload = {}
        if conflict_fields:
            result.manual_review_required = True
            result.notes = "conflicting_fields:" + ",".join(conflict_fields)
        return result

    # MANUAL_REVIEW
    result.manual_review_required = True
    result.winner_source = ""
    result.winner_payload = dict(remote.payload)  # tentative pre-review state
    result.loser_payload = dict(local.payload)
    result.notes = "manual_review_required_by_policy"
    return result


# --- Batch resolver -------------------------------------------------------


@dataclass
class BatchResolutionReport:
    auto_resolved: int = 0
    manual_review: int = 0
    no_op_identical: int = 0
    resolutions: list[ConflictResolution] = field(default_factory=list)


def resolve_batch(
    *,
    pairs: list[tuple[SyncRecord, SyncRecord]],
    strategy_overrides: dict[str, str] | None = None,
) -> BatchResolutionReport:
    """Resolve a batch of (local, remote) conflict pairs."""
    overrides = strategy_overrides or {}
    report = BatchResolutionReport()
    for local, remote in pairs:
        strategy = overrides.get(local.record_type)
        r = resolve_conflict(local=local, remote=remote, strategy=strategy)
        report.resolutions.append(r)
        if r.notes == "no_diff":
            report.no_op_identical += 1
        elif r.manual_review_required:
            report.manual_review += 1
        else:
            report.auto_resolved += 1
    return report
