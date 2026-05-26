"""Wave S-D (v3.96.1 — 2026-05-26) — Records-hold + transcript-release kernel.

A school cannot release a student's transcript to a third party (next school,
university, employer) while a "records hold" is active for that student.
Counsel-pending categories (financial, disciplinary, library, academic,
counsel_review) are codified so the policy gate is a single ``can_release``
function — both the parent portal and the registrar tool route through it.

The policy framework is shippable today; whether each individual category
is hard-blocking vs. soft-warning per jurisdiction is a counsel-pending
decision documented in ``docs/RECORDS_HOLD_COUNSEL_REVIEW.md`` (this wave
also writes that docket).

Storage: ``School.settings["records_holds"][student_id]`` → list of HoldEntry
dicts. ZERO new migrations.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass(frozen=True)
class HoldCategory:
    key: str
    label: str
    default_severity: str  # "hard" | "soft"
    counsel_pending: bool = False


_CATEGORIES: dict[str, HoldCategory] = {
    "financial": HoldCategory("financial", "Outstanding fees / balance", "hard"),
    "disciplinary": HoldCategory(
        "disciplinary", "Disciplinary review in progress",
        "soft", counsel_pending=True,
    ),
    "library": HoldCategory("library", "Library materials not returned", "soft"),
    "academic": HoldCategory(
        "academic", "Academic / credit hours not met", "hard",
    ),
    "counsel_review": HoldCategory(
        "counsel_review", "Counsel review pending",
        "hard", counsel_pending=True,
    ),
    "incomplete_paperwork": HoldCategory(
        "incomplete_paperwork", "Required paperwork incomplete", "soft",
    ),
}


def list_categories() -> list[HoldCategory]:
    return list(_CATEGORIES.values())


def get_category(key: str) -> HoldCategory | None:
    return _CATEGORIES.get(key)


# --- FSM ------------------------------------------------------------------


ACTIVE = "ACTIVE"
RESOLVED = "RESOLVED"
ESCALATED = "ESCALATED"
ALL_STAGES = (ACTIVE, RESOLVED, ESCALATED)

_TRANSITIONS: dict[str, frozenset[str]] = {
    ACTIVE: frozenset({RESOLVED, ESCALATED}),
    ESCALATED: frozenset({RESOLVED, ACTIVE}),
    RESOLVED: frozenset(),
}


class InvalidHoldTransition(ValueError):
    pass


def can_transition(current: str, target: str) -> bool:
    return target in _TRANSITIONS.get(current, frozenset())


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# --- Hold shape -----------------------------------------------------------


@dataclass
class HoldEntry:
    hold_id: str
    school_id: int
    student_id: int
    category_key: str
    severity: str  # "hard" | "soft"
    stage: str
    reason: str
    created_by_user_id: int | None
    created_at: str
    updated_at: str
    resolved_by_user_id: int | None = None
    resolved_at: str = ""
    history: list[dict] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "hold_id": self.hold_id,
            "school_id": self.school_id,
            "student_id": self.student_id,
            "category_key": self.category_key,
            "severity": self.severity,
            "stage": self.stage,
            "reason": self.reason,
            "created_by_user_id": self.created_by_user_id,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "resolved_by_user_id": self.resolved_by_user_id,
            "resolved_at": self.resolved_at,
            "history": list(self.history),
        }


def create_hold(
    *,
    school_id: int,
    student_id: int,
    category_key: str,
    reason: str,
    actor_user_id: int | None = None,
    severity_override: str | None = None,
) -> HoldEntry:
    category = get_category(category_key)
    if category is None:
        raise ValueError(f"unknown_hold_category:{category_key}")
    if not reason or len(reason.strip()) < 5:
        raise ValueError("reason_min_5_chars")
    severity = severity_override or category.default_severity
    if severity not in ("hard", "soft"):
        raise ValueError(f"invalid_severity:{severity}")
    now = _now_iso()
    hold_id = str(uuid.uuid4())
    return HoldEntry(
        hold_id=hold_id, school_id=school_id, student_id=student_id,
        category_key=category.key, severity=severity, stage=ACTIVE,
        reason=reason.strip()[:500],
        created_by_user_id=actor_user_id,
        created_at=now, updated_at=now,
        history=[{"at": now, "from": "", "to": ACTIVE, "actor_id": actor_user_id}],
    )


def transition_hold(
    *,
    hold: HoldEntry,
    target_stage: str,
    actor_user_id: int,
    note: str = "",
) -> HoldEntry:
    if target_stage not in ALL_STAGES:
        raise ValueError(f"unknown_hold_stage:{target_stage}")
    if not can_transition(hold.stage, target_stage):
        raise InvalidHoldTransition(
            f"Cannot transition hold from {hold.stage!r} to {target_stage!r}"
        )
    now = _now_iso()
    new_history = list(hold.history)
    new_history.append({
        "at": now, "from": hold.stage, "to": target_stage,
        "actor_id": actor_user_id, "note": (note or "")[:240],
    })
    return HoldEntry(
        hold_id=hold.hold_id,
        school_id=hold.school_id,
        student_id=hold.student_id,
        category_key=hold.category_key,
        severity=hold.severity,
        stage=target_stage,
        reason=hold.reason,
        created_by_user_id=hold.created_by_user_id,
        created_at=hold.created_at,
        updated_at=now,
        resolved_by_user_id=actor_user_id if target_stage == RESOLVED else hold.resolved_by_user_id,
        resolved_at=now if target_stage == RESOLVED else hold.resolved_at,
        history=new_history,
    )


# --- Release decision -----------------------------------------------------


@dataclass
class ReleaseDecision:
    student_id: int
    can_release: bool
    hard_blockers: list[str] = field(default_factory=list)
    soft_warnings: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "student_id": self.student_id,
            "can_release": self.can_release,
            "hard_blockers": list(self.hard_blockers),
            "soft_warnings": list(self.soft_warnings),
        }


def can_release_transcript(
    *,
    student_id: int,
    holds: list[HoldEntry],
) -> ReleaseDecision:
    decision = ReleaseDecision(student_id=student_id, can_release=True)
    for hold in holds:
        if hold.student_id != student_id:
            continue
        if hold.stage != ACTIVE and hold.stage != ESCALATED:
            continue
        label = f"{hold.category_key}:{hold.reason[:80]}"
        if hold.severity == "hard":
            decision.hard_blockers.append(label)
        else:
            decision.soft_warnings.append(label)
    decision.can_release = not decision.hard_blockers
    return decision


# --- Storage helpers ------------------------------------------------------


_LEDGER_CAP_PER_STUDENT = 100


def append_hold_to_settings(
    *, school_settings: dict[str, Any] | None, hold: HoldEntry,
) -> dict[str, Any]:
    settings = dict(school_settings or {})
    bucket = dict(settings.get("records_holds") or {})
    key = str(hold.student_id)
    student_holds = list(bucket.get(key) or [])
    student_holds = [h for h in student_holds if h.get("hold_id") != hold.hold_id]
    student_holds.append(hold.as_dict())
    if len(student_holds) > _LEDGER_CAP_PER_STUDENT:
        student_holds = student_holds[-_LEDGER_CAP_PER_STUDENT:]
    bucket[key] = student_holds
    settings["records_holds"] = bucket
    return settings


def active_holds_for_student(
    *, school_settings: dict[str, Any] | None, student_id: int,
) -> list[dict]:
    bucket = (school_settings or {}).get("records_holds") or {}
    rows = bucket.get(str(student_id)) or []
    return [h for h in rows if h.get("stage") in (ACTIVE, ESCALATED)]
