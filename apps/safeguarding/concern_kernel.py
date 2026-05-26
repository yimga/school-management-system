"""Wave R-D (v3.96.0 — 2026-05-26) — Safeguarding concern kernel.

The kernel is deliberately storage-agnostic: it returns the next-state +
the audit row + the persistent ledger entry. Caller writes them. This
makes the FSM + KCSIE categories testable without spinning up Django's
audit chain.

Concern lifecycle (FSM):

    DRAFT ─→ SUBMITTED ─→ ACKNOWLEDGED ─→ ACTION_TAKEN ─→ CLOSED
                                  │
                                  └──→ REFERRED_EXTERNAL ─→ CLOSED

Audit invariants:
- Every transition writes one ``CRITICAL``-sensitivity row.
- Concern body text is sanitized: PII regex pass (email / phone-like) so the
  ledger holds the narrative shape but not contact strings (those belong on
  the StudentProfile / Guardian rows, not duplicated here).
- DSL-only stages require ``dsl_user_id`` in the args; the kernel raises a
  typed exception if absent.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


# --- KCSIE 2026 category registry -----------------------------------------


@dataclass(frozen=True)
class SafeguardingCategory:
    key: str
    label: str
    is_urgent: bool = False


_CATEGORIES: dict[str, SafeguardingCategory] = {
    "physical_abuse": SafeguardingCategory("physical_abuse", "Physical abuse", True),
    "emotional_abuse": SafeguardingCategory("emotional_abuse", "Emotional abuse"),
    "neglect": SafeguardingCategory("neglect", "Neglect"),
    "sexual_abuse": SafeguardingCategory("sexual_abuse", "Sexual abuse", True),
    "child_on_child_abuse": SafeguardingCategory(
        "child_on_child_abuse", "Child-on-child abuse",
    ),
    "online_harm": SafeguardingCategory("online_harm", "Online harm"),
    "exploitation": SafeguardingCategory(
        "exploitation", "Criminal / sexual exploitation", True,
    ),
    "radicalisation": SafeguardingCategory(
        "radicalisation", "Radicalisation (Prevent duty)",
    ),
    "fgm": SafeguardingCategory("fgm", "FGM concern", True),
    "mental_health": SafeguardingCategory("mental_health", "Mental health"),
    "domestic_abuse": SafeguardingCategory("domestic_abuse", "Domestic abuse"),
    "self_harm": SafeguardingCategory("self_harm", "Self-harm", True),
    "other": SafeguardingCategory("other", "Other"),
}


def list_categories() -> list[SafeguardingCategory]:
    return list(_CATEGORIES.values())


def get_category(key: str) -> SafeguardingCategory | None:
    return _CATEGORIES.get(key)


# --- FSM ------------------------------------------------------------------


DRAFT = "DRAFT"
SUBMITTED = "SUBMITTED"
ACKNOWLEDGED = "ACKNOWLEDGED"
ACTION_TAKEN = "ACTION_TAKEN"
REFERRED_EXTERNAL = "REFERRED_EXTERNAL"
CLOSED = "CLOSED"

ALL_STAGES = (
    DRAFT, SUBMITTED, ACKNOWLEDGED, ACTION_TAKEN, REFERRED_EXTERNAL, CLOSED,
)
_DSL_ONLY_STAGES = frozenset({ACKNOWLEDGED, ACTION_TAKEN, REFERRED_EXTERNAL, CLOSED})

_TRANSITIONS: dict[str, frozenset[str]] = {
    DRAFT: frozenset({SUBMITTED}),
    SUBMITTED: frozenset({ACKNOWLEDGED}),
    ACKNOWLEDGED: frozenset({ACTION_TAKEN, REFERRED_EXTERNAL, CLOSED}),
    ACTION_TAKEN: frozenset({REFERRED_EXTERNAL, CLOSED}),
    REFERRED_EXTERNAL: frozenset({CLOSED}),
    CLOSED: frozenset(),
}


class InvalidConcernTransition(ValueError):
    pass


class DSLRoleRequired(PermissionError):
    """Raised when a DSL-only stage transition lacks ``dsl_user_id``."""


def can_transition(current: str, target: str) -> bool:
    return target in _TRANSITIONS.get(current, frozenset())


# --- PII sanitization for narrative bodies --------------------------------


_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_PHONE_RE = re.compile(r"(\+?\d[\d\s\-()]{6,}\d)")
_MAX_NARRATIVE = 4000


def sanitize_narrative(text: str) -> str:
    """Strip emails / phone-like sequences from a free-text narrative."""
    if not text:
        return ""
    text = text[:_MAX_NARRATIVE]
    text = _EMAIL_RE.sub("[REDACTED_EMAIL]", text)
    text = _PHONE_RE.sub("[REDACTED_PHONE]", text)
    return text


# --- DSL role verifier ----------------------------------------------------


@dataclass(frozen=True)
class DSLAssignment:
    user_id: int
    school_id: int
    is_active: bool = True


def is_dsl(user_id: int | None, school_id: int, dsl_assignments: list[DSLAssignment]) -> bool:
    if user_id is None:
        return False
    for d in dsl_assignments:
        if d.user_id == user_id and d.school_id == school_id and d.is_active:
            return True
    return False


# --- Concern shape --------------------------------------------------------


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class ConcernEntry:
    concern_id: str
    school_id: int
    student_id: int | None
    reporter_user_id: int
    category_key: str
    stage: str
    narrative: str
    is_urgent: bool
    created_at: str
    updated_at: str
    history: list[dict] = field(default_factory=list)
    dsl_acknowledged_by: int | None = None
    dsl_acknowledged_at: str = ""
    referral_reference: str = ""

    def as_dict(self) -> dict:
        return {
            "concern_id": self.concern_id,
            "school_id": self.school_id,
            "student_id": self.student_id,
            "reporter_user_id": self.reporter_user_id,
            "category_key": self.category_key,
            "stage": self.stage,
            "narrative": self.narrative,
            "is_urgent": self.is_urgent,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "history": list(self.history),
            "dsl_acknowledged_by": self.dsl_acknowledged_by,
            "dsl_acknowledged_at": self.dsl_acknowledged_at,
            "referral_reference": self.referral_reference,
        }


@dataclass
class AuditRow:
    """Shape mirrored from ``apps.compliance.models_audit.AuditLog``."""

    action: str
    model_name: str = "SafeguardingConcern"
    object_id: str = ""
    sensitivity: str = "CRITICAL"
    new_values: dict[str, Any] = field(default_factory=dict)
    reason: str = ""
    user_id: int | None = None
    app_label: str = "safeguarding"


# --- Public API -----------------------------------------------------------


def create_concern(
    *,
    school_id: int,
    student_id: int | None,
    reporter_user_id: int,
    category_key: str,
    narrative: str,
) -> tuple[ConcernEntry, AuditRow]:
    cat = get_category(category_key)
    if cat is None:
        raise ValueError(f"Unknown safeguarding category: {category_key!r}")
    if not narrative or len(narrative.strip()) < 10:
        raise ValueError("Narrative must be at least 10 characters.")

    concern_id = str(uuid.uuid4())
    now = _now_iso()
    entry = ConcernEntry(
        concern_id=concern_id,
        school_id=school_id,
        student_id=student_id,
        reporter_user_id=reporter_user_id,
        category_key=cat.key,
        stage=DRAFT,
        narrative=sanitize_narrative(narrative),
        is_urgent=cat.is_urgent,
        created_at=now,
        updated_at=now,
        history=[{"at": now, "from": "", "to": DRAFT, "actor_id": reporter_user_id}],
    )
    audit = AuditRow(
        action="CREATE",
        object_id=concern_id,
        new_values={"category": cat.key, "is_urgent": cat.is_urgent, "stage": DRAFT},
        reason="safeguarding.concern.created",
        user_id=reporter_user_id,
    )
    return entry, audit


def transition_concern(
    *,
    concern: ConcernEntry,
    target_stage: str,
    actor_user_id: int,
    dsl_assignments: list[DSLAssignment] | None = None,
    note: str = "",
    referral_reference: str = "",
) -> tuple[ConcernEntry, AuditRow]:
    if target_stage not in ALL_STAGES:
        raise ValueError(f"Unknown concern stage: {target_stage!r}")
    if not can_transition(concern.stage, target_stage):
        raise InvalidConcernTransition(
            f"Cannot transition concern from {concern.stage!r} to {target_stage!r}."
        )
    if target_stage in _DSL_ONLY_STAGES:
        dsls = dsl_assignments or []
        if not is_dsl(actor_user_id, concern.school_id, dsls):
            raise DSLRoleRequired(
                "Only an active Designated Safeguarding Lead can advance the "
                "concern past SUBMITTED."
            )

    now = _now_iso()
    new_history = list(concern.history)
    new_history.append({
        "at": now,
        "from": concern.stage,
        "to": target_stage,
        "actor_id": actor_user_id,
        "note": (note or "")[:240],
    })
    new = ConcernEntry(
        concern_id=concern.concern_id,
        school_id=concern.school_id,
        student_id=concern.student_id,
        reporter_user_id=concern.reporter_user_id,
        category_key=concern.category_key,
        stage=target_stage,
        narrative=concern.narrative,
        is_urgent=concern.is_urgent,
        created_at=concern.created_at,
        updated_at=now,
        history=new_history,
        dsl_acknowledged_by=(
            actor_user_id if target_stage == ACKNOWLEDGED else concern.dsl_acknowledged_by
        ),
        dsl_acknowledged_at=(
            now if target_stage == ACKNOWLEDGED else concern.dsl_acknowledged_at
        ),
        referral_reference=(
            referral_reference if target_stage == REFERRED_EXTERNAL
            else concern.referral_reference
        ),
    )
    audit = AuditRow(
        action="UPDATE",
        object_id=concern.concern_id,
        new_values={
            "stage_from": concern.stage,
            "stage_to": target_stage,
            "is_urgent": concern.is_urgent,
        },
        reason=f"safeguarding.concern.transition:{target_stage}",
        user_id=actor_user_id,
    )
    return new, audit


# --- Ledger storage helper (School.settings["safeguarding"]["concerns"]) --


_LEDGER_CAP = 500


def append_to_school_settings(
    *,
    school_settings: dict[str, Any] | None,
    concern: ConcernEntry,
) -> dict[str, Any]:
    settings = dict(school_settings or {})
    bucket = dict(settings.get("safeguarding") or {})
    concerns = list(bucket.get("concerns") or [])
    concerns = [c for c in concerns if c.get("concern_id") != concern.concern_id]
    concerns.append(concern.as_dict())
    if len(concerns) > _LEDGER_CAP:
        concerns = concerns[-_LEDGER_CAP:]
    bucket["concerns"] = concerns
    settings["safeguarding"] = bucket
    return settings


def open_concerns(school_settings: dict[str, Any] | None) -> list[dict]:
    bucket = (school_settings or {}).get("safeguarding") or {}
    return [c for c in (bucket.get("concerns") or []) if c.get("stage") != CLOSED]
