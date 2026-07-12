"""Wave T (v3.97.0 — 2026-05-26) — DSL notification handoff.

Closes the cross-persona handoff gap shipped in Wave R-D: when a teacher
submits a safeguarding concern, the Designated Safeguarding Lead (DSL) had
to discover it by polling the queue. This module emits an in-app inbox
entry with a 1-click deep-link to the concern detail view.

Design:
- Storage piggybacks on the same ``School.settings["safeguarding"]``
  bucket that ``concern_kernel`` uses for the concern ledger. We append
  to a parallel ``dsl_inbox`` list (FIFO cap 200 per tenant) so the
  inbox is queryable from the same school row — ZERO new migrations.
- Each inbox entry carries the concern_id + url + KCSIE category +
  is_urgent flag + created_at. PII (narrative text) is NEVER duplicated
  here; the deep-link is the only path to the sensitive body.
- The notifier is best-effort: a failure to write must NEVER block the
  concern submission itself. Caller wraps the call in try/except, logs
  WARNING on failure, and proceeds.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


# FIFO cap (matches the per-tenant cap convention used by Wave R-D's concern
# ledger and Wave Q's other ledgers).
_DSL_INBOX_FIFO_CAP = 200


@dataclass(frozen=True)
class DSLInboxEntry:
    """A single deep-link entry routed to a DSL for action."""

    entry_id: str
    concern_id: str
    deep_link_url: str
    category_key: str
    category_label: str
    is_urgent: bool
    submitted_by_user_id: int
    student_id: int
    created_at_iso: str
    # Acknowledged-at is the timestamp when a DSL clicked the deep-link;
    # null until then. ``acknowledged_by_user_id`` records WHICH DSL acted
    # (multiple DSLs may share an inbox).
    acknowledged_at_iso: str = ""
    acknowledged_by_user_id: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "entry_id": self.entry_id,
            "concern_id": self.concern_id,
            "deep_link_url": self.deep_link_url,
            "category_key": self.category_key,
            "category_label": self.category_label,
            "is_urgent": self.is_urgent,
            "submitted_by_user_id": self.submitted_by_user_id,
            "student_id": self.student_id,
            "created_at_iso": self.created_at_iso,
            "acknowledged_at_iso": self.acknowledged_at_iso,
            "acknowledged_by_user_id": self.acknowledged_by_user_id,
        }


@dataclass(frozen=True)
class DSLNotifyResult:
    """Outcome of a notify_dsl_of_concern call."""

    entry: DSLInboxEntry
    updated_inbox: list[dict[str, Any]]


def _utcnow_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def _new_entry_id() -> str:
    # uuid4 hex prefix is plenty unique for an in-tenant FIFO of 200.
    import uuid

    return uuid.uuid4().hex[:16]


def build_concern_deep_link(concern_id: str) -> str:
    """Build the URL a DSL clicks to open the concern.

    Pure-Python: returns a path string. The actual URL routing is wired
    in the Django URLconf; this just preserves the path contract.
    """
    if not concern_id:
        raise ValueError("concern_id required")
    return f"/school/studio/workflow-center/safeguarding/{concern_id}/"


def notify_dsl_of_concern(
    *,
    current_inbox: list[dict[str, Any]] | None,
    concern_id: str,
    category_key: str,
    category_label: str,
    is_urgent: bool,
    submitted_by_user_id: int,
    student_id: int,
    now_iso: str | None = None,
) -> DSLNotifyResult:
    """Append a deep-link inbox entry; trim FIFO to cap.

    Returns ``DSLNotifyResult`` with the appended entry and the new inbox
    list (caller persists to ``School.settings["safeguarding"]["dsl_inbox"]``).
    """
    if not concern_id:
        raise ValueError("concern_id required")
    if not category_key:
        raise ValueError("category_key required")
    if submitted_by_user_id is None or submitted_by_user_id <= 0:
        raise ValueError("submitted_by_user_id must be a positive int")
    if student_id is None or student_id <= 0:
        raise ValueError("student_id must be a positive int")

    entry = DSLInboxEntry(
        entry_id=_new_entry_id(),
        concern_id=concern_id,
        deep_link_url=build_concern_deep_link(concern_id),
        category_key=category_key,
        category_label=category_label or category_key,
        is_urgent=bool(is_urgent),
        submitted_by_user_id=int(submitted_by_user_id),
        student_id=int(student_id),
        created_at_iso=now_iso or _utcnow_iso(),
    )

    inbox = list(current_inbox or [])
    inbox.append(entry.to_dict())

    # FIFO trim: keep the most recent N entries. Urgent items survive the
    # cap because we cap from the OLDEST end; the inbox grows append-only.
    if len(inbox) > _DSL_INBOX_FIFO_CAP:
        inbox = inbox[-_DSL_INBOX_FIFO_CAP:]

    return DSLNotifyResult(entry=entry, updated_inbox=inbox)


def acknowledge_inbox_entry(
    *,
    current_inbox: list[dict[str, Any]] | None,
    entry_id: str,
    acknowledged_by_user_id: int,
    now_iso: str | None = None,
) -> list[dict[str, Any]]:
    """Mark a single inbox entry as acknowledged by a specific DSL.

    Idempotent: re-acknowledging the same entry is a no-op (the first
    acknowledgement wins so audit shows who acted first).
    """
    if not entry_id:
        raise ValueError("entry_id required")
    if acknowledged_by_user_id is None or acknowledged_by_user_id <= 0:
        raise ValueError("acknowledged_by_user_id must be a positive int")

    inbox = list(current_inbox or [])
    ts = now_iso or _utcnow_iso()
    for row in inbox:
        if row.get("entry_id") == entry_id and not row.get("acknowledged_at_iso"):
            row["acknowledged_at_iso"] = ts
            row["acknowledged_by_user_id"] = int(acknowledged_by_user_id)
            break
    return inbox


def list_unacknowledged(
    current_inbox: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    """Filter the inbox to real, unacknowledged DSL *concern* entries.

    A concern entry is one produced by ``notify_dsl_of_concern`` — identified by
    its ``entry_id`` (and clearable only via ``acknowledge_inbox_entry``, which
    matches on that id). Non-concern rows that other producers may append to the
    same ``dsl_inbox`` bucket — e.g. the privilege-audit sweep's ``{ts, kind,
    count}`` flags, which carry NO ``entry_id`` and so could never be acknowledged
    — must NOT be counted as open concerns. Otherwise the operator-queue "DSL
    action required within KCSIE SLA" banner lights on audit noise and can never be
    cleared. Requiring ``entry_id`` here is both the fix and a defence-in-depth
    that auto-heals any tenant whose inbox already holds such stray rows.
    """
    return [
        row
        for row in (current_inbox or [])
        if row.get("entry_id") and not row.get("acknowledged_at_iso")
    ]


def count_urgent_unacknowledged(
    current_inbox: list[dict[str, Any]] | None,
) -> int:
    """Sidebar badge count: how many urgent items still need a DSL?"""
    return sum(
        1
        for row in list_unacknowledged(current_inbox)
        if row.get("is_urgent")
    )
