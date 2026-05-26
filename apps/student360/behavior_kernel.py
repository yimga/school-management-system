"""Wave S-C (v3.96.1 — 2026-05-26) — Behavior incidents + recognition kernel.

Two faces of the same ledger:

- **Recognitions** (positive) — student earned commendations: respect, effort,
  citizenship, kindness, leadership, academic_excellence. Each recognition
  carries a point value (default +1).
- **Infractions** (corrective) — tardiness, disruption, uniform_violation,
  unauthorized_device, peer_conflict, academic_dishonesty,
  property_misuse, missed_assignment, late_to_class, bullying.
  Each carries a point value (negative, default -1) and a severity tier
  (minor / moderate / severe).

The kernel ships:

- ``record_behavior_event(...)`` — produces a typed event + an audit row.
- ``compute_student_point_total(events)`` — sums points within a window.
- ``compute_house_totals(events_by_house)`` — aggregator for inter-house
  competitions (the most common school-life gamification anchor).
- ``check_escalation(student_events, today, window_days)`` — returns a
  ``SuggestedEscalation`` when an infraction pattern exceeds policy
  thresholds (3+ moderate infractions in 30 days → "DSL / counsellor
  meeting recommended", etc.).

Storage: ``School.settings["behavior"]["events"]`` (FIFO cap 5000).
ZERO new migrations.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from datetime import date as date_type
from datetime import timedelta
from typing import Any


# --- Category registries --------------------------------------------------


@dataclass(frozen=True)
class BehaviorCategory:
    key: str
    label: str
    polarity: str  # "positive" | "negative"
    default_points: int
    severity: str = "minor"  # "minor" | "moderate" | "severe" (negative only)


_POSITIVE_CATEGORIES: dict[str, BehaviorCategory] = {
    "respect": BehaviorCategory("respect", "Respect", "positive", 1),
    "effort": BehaviorCategory("effort", "Effort", "positive", 1),
    "citizenship": BehaviorCategory("citizenship", "Citizenship", "positive", 2),
    "kindness": BehaviorCategory("kindness", "Kindness", "positive", 2),
    "leadership": BehaviorCategory("leadership", "Leadership", "positive", 3),
    "academic_excellence": BehaviorCategory(
        "academic_excellence", "Academic excellence", "positive", 3,
    ),
}

_NEGATIVE_CATEGORIES: dict[str, BehaviorCategory] = {
    "tardiness": BehaviorCategory(
        "tardiness", "Tardiness", "negative", -1, severity="minor",
    ),
    "uniform_violation": BehaviorCategory(
        "uniform_violation", "Uniform violation", "negative", -1, severity="minor",
    ),
    "unauthorized_device": BehaviorCategory(
        "unauthorized_device", "Unauthorized device", "negative", -2, severity="minor",
    ),
    "disruption": BehaviorCategory(
        "disruption", "Classroom disruption", "negative", -2, severity="moderate",
    ),
    "late_to_class": BehaviorCategory(
        "late_to_class", "Late to class", "negative", -1, severity="minor",
    ),
    "missed_assignment": BehaviorCategory(
        "missed_assignment", "Missed assignment", "negative", -2, severity="moderate",
    ),
    "property_misuse": BehaviorCategory(
        "property_misuse", "Property misuse", "negative", -3, severity="moderate",
    ),
    "peer_conflict": BehaviorCategory(
        "peer_conflict", "Peer conflict", "negative", -3, severity="moderate",
    ),
    "academic_dishonesty": BehaviorCategory(
        "academic_dishonesty", "Academic dishonesty", "negative", -5, severity="severe",
    ),
    "bullying": BehaviorCategory(
        "bullying", "Bullying", "negative", -5, severity="severe",
    ),
}


def list_positive_categories() -> list[BehaviorCategory]:
    return list(_POSITIVE_CATEGORIES.values())


def list_negative_categories() -> list[BehaviorCategory]:
    return list(_NEGATIVE_CATEGORIES.values())


def get_category(key: str) -> BehaviorCategory | None:
    return _POSITIVE_CATEGORIES.get(key) or _NEGATIVE_CATEGORIES.get(key)


# --- Event shape ----------------------------------------------------------


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class BehaviorEvent:
    event_id: str
    school_id: int
    student_id: int
    house_key: str  # may be empty if school has no houses
    reporter_user_id: int
    category_key: str
    polarity: str
    severity: str
    points: int
    occurred_at: str  # ISO datetime
    note: str = ""

    def as_dict(self) -> dict:
        return {
            "event_id": self.event_id,
            "school_id": self.school_id,
            "student_id": self.student_id,
            "house_key": self.house_key,
            "reporter_user_id": self.reporter_user_id,
            "category_key": self.category_key,
            "polarity": self.polarity,
            "severity": self.severity,
            "points": self.points,
            "occurred_at": self.occurred_at,
            "note": self.note,
        }


@dataclass
class AuditRow:
    action: str
    model_name: str = "BehaviorEvent"
    object_id: str = ""
    sensitivity: str = "MEDIUM"  # severe gets bumped to HIGH below
    new_values: dict = field(default_factory=dict)
    reason: str = ""
    user_id: int | None = None
    app_label: str = "student360"


def record_behavior_event(
    *,
    school_id: int,
    student_id: int,
    reporter_user_id: int,
    category_key: str,
    house_key: str = "",
    points_override: int | None = None,
    note: str = "",
    occurred_at_iso: str | None = None,
) -> tuple[BehaviorEvent, AuditRow]:
    category = get_category(category_key)
    if category is None:
        raise ValueError(f"unknown_behavior_category:{category_key}")
    note_clean = (note or "")[:1000]
    event_id = str(uuid.uuid4())
    occurred = occurred_at_iso or _now_iso()
    points = points_override if points_override is not None else category.default_points
    event = BehaviorEvent(
        event_id=event_id,
        school_id=school_id,
        student_id=student_id,
        house_key=house_key[:60],
        reporter_user_id=reporter_user_id,
        category_key=category.key,
        polarity=category.polarity,
        severity=category.severity,
        points=points,
        occurred_at=occurred,
        note=note_clean,
    )
    sensitivity = "HIGH" if category.severity == "severe" else "MEDIUM"
    audit = AuditRow(
        action="CREATE",
        object_id=event_id,
        sensitivity=sensitivity,
        new_values={
            "category": category.key, "polarity": category.polarity,
            "severity": category.severity, "points": points,
        },
        reason=f"behavior.{category.polarity}.recorded",
        user_id=reporter_user_id,
    )
    return event, audit


# --- Aggregators ----------------------------------------------------------


def compute_student_point_total(
    *, events: list[BehaviorEvent], student_id: int,
) -> int:
    return sum(e.points for e in events if e.student_id == student_id)


def compute_house_totals(
    *, events: list[BehaviorEvent],
) -> dict[str, int]:
    totals: dict[str, int] = {}
    for e in events:
        if not e.house_key:
            continue
        totals[e.house_key] = totals.get(e.house_key, 0) + e.points
    return totals


@dataclass
class SuggestedEscalation:
    student_id: int
    severity_label: str  # "notice" | "counsellor_meeting" | "parent_conference" | "dsl_review"
    moderate_in_window: int
    severe_in_window: int
    window_days: int
    rationale: str


def check_escalation(
    *,
    student_id: int,
    events: list[BehaviorEvent],
    today: date_type,
    window_days: int = 30,
) -> SuggestedEscalation | None:
    """Return an escalation suggestion when infraction counts cross thresholds."""
    cutoff = today - timedelta(days=window_days)
    moderate = 0
    severe = 0
    for e in events:
        if e.student_id != student_id or e.polarity != "negative":
            continue
        try:
            event_date = datetime.fromisoformat(e.occurred_at).date()
        except (ValueError, TypeError):
            continue
        if event_date < cutoff:
            continue
        if e.severity == "severe":
            severe += 1
        elif e.severity == "moderate":
            moderate += 1
    if severe >= 1:
        return SuggestedEscalation(
            student_id=student_id, severity_label="dsl_review",
            moderate_in_window=moderate, severe_in_window=severe,
            window_days=window_days,
            rationale="severe_infraction_recorded",
        )
    if moderate >= 5:
        return SuggestedEscalation(
            student_id=student_id, severity_label="parent_conference",
            moderate_in_window=moderate, severe_in_window=0,
            window_days=window_days,
            rationale=f"{moderate}_moderate_infractions_in_{window_days}_days",
        )
    if moderate >= 3:
        return SuggestedEscalation(
            student_id=student_id, severity_label="counsellor_meeting",
            moderate_in_window=moderate, severe_in_window=0,
            window_days=window_days,
            rationale=f"{moderate}_moderate_infractions_in_{window_days}_days",
        )
    if moderate >= 1:
        return SuggestedEscalation(
            student_id=student_id, severity_label="notice",
            moderate_in_window=moderate, severe_in_window=0,
            window_days=window_days,
            rationale="moderate_infraction_recorded",
        )
    return None


# --- Storage helper -------------------------------------------------------


_LEDGER_CAP = 5000


def append_behavior_event_to_settings(
    *, school_settings: dict[str, Any] | None, event: BehaviorEvent,
) -> dict[str, Any]:
    settings = dict(school_settings or {})
    bucket = dict(settings.get("behavior") or {})
    events = list(bucket.get("events") or [])
    events.append(event.as_dict())
    if len(events) > _LEDGER_CAP:
        events = events[-_LEDGER_CAP:]
    bucket["events"] = events
    settings["behavior"] = bucket
    return settings
