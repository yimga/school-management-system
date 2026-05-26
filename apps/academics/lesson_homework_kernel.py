"""Wave S-B (v3.96.1 — 2026-05-26) — Lesson plan + homework lifecycle kernel.

Two related objects share one FSM-style lifecycle and one storage shape:

- ``LessonPlan`` — teacher's prep doc for a single class period. Has
  objectives + activities + assessments + (optional) standards alignment.
- ``Homework`` — student-facing task with due date, instructions, optional
  attachment references.

Both live behind the same lifecycle:

    DRAFT ─→ PUBLISHED ─→ DUE ─→ CLOSED
                  └────→ ARCHIVED

For homework, ``submit_student_work`` records a per-student submission
without changing the homework's own stage. ``check_overdue_homeworks(today)``
returns the slice of published homeworks whose due_date has passed — used
by the nudge engine.

ZERO new migrations. Persistence is School.settings JSONField:
- ``School.settings["academics"]["lesson_plans"][lesson_id]``
- ``School.settings["academics"]["homeworks"][homework_id]``
- ``School.settings["academics"]["homework_submissions"][homework_id][student_id]``

Each bucket is FIFO-capped at 2000 entries.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date as date_type
from datetime import datetime, timezone
from typing import Any


DRAFT = "DRAFT"
PUBLISHED = "PUBLISHED"
DUE = "DUE"
CLOSED = "CLOSED"
ARCHIVED = "ARCHIVED"

ALL_STAGES = (DRAFT, PUBLISHED, DUE, CLOSED, ARCHIVED)

_TRANSITIONS: dict[str, frozenset[str]] = {
    DRAFT: frozenset({PUBLISHED, ARCHIVED}),
    PUBLISHED: frozenset({DUE, CLOSED, ARCHIVED}),
    DUE: frozenset({CLOSED, ARCHIVED}),
    CLOSED: frozenset({ARCHIVED}),
    ARCHIVED: frozenset(),
}


class InvalidLifecycleTransition(ValueError):
    pass


def can_transition(current: str, target: str) -> bool:
    return target in _TRANSITIONS.get(current, frozenset())


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


_LEDGER_CAP = 2000


# --- Lesson plan ----------------------------------------------------------


@dataclass
class LessonPlanBlock:
    block_type: str  # "objective" | "activity" | "assessment" | "standard"
    title: str
    duration_minutes: int = 0
    notes: str = ""

    def as_dict(self) -> dict:
        return {
            "block_type": self.block_type, "title": self.title,
            "duration_minutes": self.duration_minutes, "notes": self.notes,
        }


@dataclass
class LessonPlan:
    lesson_id: str
    school_id: int
    teacher_user_id: int
    classroom_id: int | None
    subject: str
    title: str
    blocks: list[LessonPlanBlock]
    scheduled_date: date_type | None
    stage: str = DRAFT
    created_at: str = field(default_factory=_now_iso)
    updated_at: str = field(default_factory=_now_iso)

    def as_dict(self) -> dict:
        return {
            "lesson_id": self.lesson_id,
            "school_id": self.school_id,
            "teacher_user_id": self.teacher_user_id,
            "classroom_id": self.classroom_id,
            "subject": self.subject,
            "title": self.title,
            "blocks": [b.as_dict() for b in self.blocks],
            "scheduled_date": self.scheduled_date.isoformat() if self.scheduled_date else "",
            "stage": self.stage,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


_VALID_BLOCK_TYPES = ("objective", "activity", "assessment", "standard")


def create_lesson_plan(
    *,
    school_id: int,
    teacher_user_id: int,
    classroom_id: int | None,
    subject: str,
    title: str,
    blocks: list[LessonPlanBlock],
    scheduled_date: date_type | None = None,
) -> LessonPlan:
    if not title or len(title.strip()) < 3:
        raise ValueError("title_min_3_chars")
    if not blocks:
        raise ValueError("at_least_one_block_required")
    if not any(b.block_type == "objective" for b in blocks):
        raise ValueError("at_least_one_objective_block_required")
    for b in blocks:
        if b.block_type not in _VALID_BLOCK_TYPES:
            raise ValueError(f"invalid_block_type:{b.block_type}")
        if b.duration_minutes < 0:
            raise ValueError("duration_minutes_negative")
    return LessonPlan(
        lesson_id=str(uuid.uuid4()),
        school_id=school_id,
        teacher_user_id=teacher_user_id,
        classroom_id=classroom_id,
        subject=subject[:120],
        title=title.strip()[:240],
        blocks=list(blocks),
        scheduled_date=scheduled_date,
    )


def advance_lesson_stage(
    *, lesson: LessonPlan, target_stage: str, actor_user_id: int,
) -> LessonPlan:
    if target_stage not in ALL_STAGES:
        raise ValueError(f"unknown_stage:{target_stage}")
    if not can_transition(lesson.stage, target_stage):
        raise InvalidLifecycleTransition(
            f"Cannot transition lesson from {lesson.stage!r} to {target_stage!r}"
        )
    return LessonPlan(
        lesson_id=lesson.lesson_id,
        school_id=lesson.school_id,
        teacher_user_id=lesson.teacher_user_id,
        classroom_id=lesson.classroom_id,
        subject=lesson.subject,
        title=lesson.title,
        blocks=list(lesson.blocks),
        scheduled_date=lesson.scheduled_date,
        stage=target_stage,
        created_at=lesson.created_at,
        updated_at=_now_iso(),
    )


# --- Homework -------------------------------------------------------------


@dataclass
class Homework:
    homework_id: str
    school_id: int
    teacher_user_id: int
    classroom_id: int | None
    subject: str
    title: str
    instructions: str
    assigned_student_ids: tuple[int, ...]
    due_date: date_type | None
    max_score_percent: int = 100
    attachment_refs: tuple[str, ...] = ()
    stage: str = DRAFT
    created_at: str = field(default_factory=_now_iso)
    updated_at: str = field(default_factory=_now_iso)

    def as_dict(self) -> dict:
        return {
            "homework_id": self.homework_id,
            "school_id": self.school_id,
            "teacher_user_id": self.teacher_user_id,
            "classroom_id": self.classroom_id,
            "subject": self.subject,
            "title": self.title,
            "instructions": self.instructions,
            "assigned_student_ids": list(self.assigned_student_ids),
            "due_date": self.due_date.isoformat() if self.due_date else "",
            "max_score_percent": self.max_score_percent,
            "attachment_refs": list(self.attachment_refs),
            "stage": self.stage,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


def create_homework(
    *,
    school_id: int,
    teacher_user_id: int,
    classroom_id: int | None,
    subject: str,
    title: str,
    instructions: str,
    assigned_student_ids: list[int],
    due_date: date_type | None,
    attachment_refs: list[str] | None = None,
) -> Homework:
    if not title or len(title.strip()) < 3:
        raise ValueError("title_min_3_chars")
    if not instructions or len(instructions.strip()) < 5:
        raise ValueError("instructions_min_5_chars")
    if not assigned_student_ids:
        raise ValueError("at_least_one_student_assigned")
    unique_students = tuple(sorted(set(assigned_student_ids)))
    return Homework(
        homework_id=str(uuid.uuid4()),
        school_id=school_id,
        teacher_user_id=teacher_user_id,
        classroom_id=classroom_id,
        subject=subject[:120],
        title=title.strip()[:240],
        instructions=instructions.strip()[:4000],
        assigned_student_ids=unique_students,
        due_date=due_date,
        attachment_refs=tuple(attachment_refs or []),
    )


def advance_homework_stage(
    *, homework: Homework, target_stage: str, actor_user_id: int,
) -> Homework:
    if target_stage not in ALL_STAGES:
        raise ValueError(f"unknown_stage:{target_stage}")
    if not can_transition(homework.stage, target_stage):
        raise InvalidLifecycleTransition(
            f"Cannot transition homework from {homework.stage!r} to {target_stage!r}"
        )
    return Homework(
        homework_id=homework.homework_id,
        school_id=homework.school_id,
        teacher_user_id=homework.teacher_user_id,
        classroom_id=homework.classroom_id,
        subject=homework.subject,
        title=homework.title,
        instructions=homework.instructions,
        assigned_student_ids=homework.assigned_student_ids,
        due_date=homework.due_date,
        max_score_percent=homework.max_score_percent,
        attachment_refs=homework.attachment_refs,
        stage=target_stage,
        created_at=homework.created_at,
        updated_at=_now_iso(),
    )


# --- Homework submission --------------------------------------------------


@dataclass
class HomeworkSubmission:
    homework_id: str
    student_id: int
    submitted_at: str
    submission_text: str = ""
    attachment_refs: tuple[str, ...] = ()
    score_percent: int | None = None
    late: bool = False

    def as_dict(self) -> dict:
        return {
            "homework_id": self.homework_id,
            "student_id": self.student_id,
            "submitted_at": self.submitted_at,
            "submission_text": self.submission_text,
            "attachment_refs": list(self.attachment_refs),
            "score_percent": self.score_percent,
            "late": self.late,
        }


def submit_student_work(
    *,
    homework: Homework,
    student_id: int,
    submission_text: str = "",
    attachment_refs: list[str] | None = None,
    today: date_type | None = None,
) -> HomeworkSubmission:
    if homework.stage not in (PUBLISHED, DUE):
        raise InvalidLifecycleTransition(
            f"Cannot submit work for homework in stage {homework.stage!r}"
        )
    if student_id not in homework.assigned_student_ids:
        raise ValueError("student_not_assigned_to_homework")
    is_late = False
    if homework.due_date and today and today > homework.due_date:
        is_late = True
    return HomeworkSubmission(
        homework_id=homework.homework_id,
        student_id=student_id,
        submitted_at=_now_iso(),
        submission_text=(submission_text or "")[:8000],
        attachment_refs=tuple(attachment_refs or []),
        late=is_late,
    )


# --- Aggregator helpers ---------------------------------------------------


def check_overdue_homeworks(
    *, homeworks: list[Homework], today: date_type,
) -> list[Homework]:
    return [
        h for h in homeworks
        if h.stage in (PUBLISHED, DUE)
        and h.due_date is not None
        and h.due_date < today
    ]


def per_student_overdue_count(
    *, homeworks: list[Homework], submissions: list[HomeworkSubmission],
    today: date_type,
) -> dict[int, int]:
    """For each student, count how many assigned homeworks are past-due and unsubmitted."""
    submitted_lookup: dict[str, set[int]] = {}
    for sub in submissions:
        submitted_lookup.setdefault(sub.homework_id, set()).add(sub.student_id)
    out: dict[int, int] = {}
    for hw in homeworks:
        if hw.due_date is None or hw.due_date >= today:
            continue
        if hw.stage not in (PUBLISHED, DUE):
            continue
        already_in = submitted_lookup.get(hw.homework_id, set())
        for sid in hw.assigned_student_ids:
            if sid in already_in:
                continue
            out[sid] = out.get(sid, 0) + 1
    return out


# --- Storage helpers (School.settings) ------------------------------------


def store_lesson_plan(
    *, school_settings: dict[str, Any] | None, lesson: LessonPlan,
) -> dict[str, Any]:
    settings = dict(school_settings or {})
    bucket = dict(settings.get("academics") or {})
    lessons = dict(bucket.get("lesson_plans") or {})
    lessons[lesson.lesson_id] = lesson.as_dict()
    if len(lessons) > _LEDGER_CAP:
        # FIFO: drop oldest by created_at
        ordered = sorted(lessons.items(), key=lambda kv: kv[1].get("created_at", ""))
        lessons = dict(ordered[-_LEDGER_CAP:])
    bucket["lesson_plans"] = lessons
    settings["academics"] = bucket
    return settings


def store_homework(
    *, school_settings: dict[str, Any] | None, homework: Homework,
) -> dict[str, Any]:
    settings = dict(school_settings or {})
    bucket = dict(settings.get("academics") or {})
    items = dict(bucket.get("homeworks") or {})
    items[homework.homework_id] = homework.as_dict()
    if len(items) > _LEDGER_CAP:
        ordered = sorted(items.items(), key=lambda kv: kv[1].get("created_at", ""))
        items = dict(ordered[-_LEDGER_CAP:])
    bucket["homeworks"] = items
    settings["academics"] = bucket
    return settings


def store_submission(
    *, school_settings: dict[str, Any] | None, submission: HomeworkSubmission,
) -> dict[str, Any]:
    settings = dict(school_settings or {})
    bucket = dict(settings.get("academics") or {})
    subs_by_hw = dict(bucket.get("homework_submissions") or {})
    per_hw = dict(subs_by_hw.get(submission.homework_id) or {})
    per_hw[str(submission.student_id)] = submission.as_dict()
    subs_by_hw[submission.homework_id] = per_hw
    bucket["homework_submissions"] = subs_by_hw
    settings["academics"] = bucket
    return settings
