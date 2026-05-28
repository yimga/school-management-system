"""Wave R-E (v3.96.0 — 2026-05-26) — Onboarding day-N nudges.

New tenants who haven't completed key onboarding tasks within their first 30
days get a tapered nudge schedule. The kernel is pure-function: it takes the
tenant's signup date, the set of completed task keys, and "today" — and
returns the list of nudges due to send right now.

The kernel ships ZERO new migrations. State lives on
``School.settings["customersuccess"]["nudges_sent"]`` (a list of
``"<task_key>:<day>"`` markers) so the scheduler never double-sends.

The Celery task wrapper iterates active schools, invokes ``compute_due_nudges``
for each, and emits via the existing channel_adapter. Real delivery is
already done by ``apps.communication.channel_adapter``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date as date_type
from typing import Any


# --- Onboarding task registry ---------------------------------------------


@dataclass(frozen=True)
class OnboardingTask:
    key: str
    label: str
    nudge_day_offsets: tuple[int, ...]
    # Channel preference order — first available wins.
    channels: tuple[str, ...] = ("in_app", "email")


_TASKS: dict[str, OnboardingTask] = {
    "import_students": OnboardingTask(
        key="import_students",
        label="Import your first student roster",
        nudge_day_offsets=(2, 5, 10, 21),
    ),
    "configure_branding": OnboardingTask(
        key="configure_branding",
        label="Add your school logo and brand colors",
        nudge_day_offsets=(3, 7, 14),
    ),
    "invite_teachers": OnboardingTask(
        key="invite_teachers",
        label="Invite at least one teacher",
        nudge_day_offsets=(2, 7, 14, 21),
    ),
    "set_up_fees": OnboardingTask(
        key="set_up_fees",
        label="Configure your fee plan",
        nudge_day_offsets=(5, 10, 21),
    ),
    "first_announcement": OnboardingTask(
        key="first_announcement",
        label="Send your first parent announcement",
        nudge_day_offsets=(7, 14),
    ),
    "calendar_setup": OnboardingTask(
        key="calendar_setup",
        label="Confirm the academic calendar for your region",
        nudge_day_offsets=(2, 6),
    ),
    "complete_setup_studio": OnboardingTask(
        key="complete_setup_studio",
        label="Finish Setup Studio launch wizard",
        nudge_day_offsets=(1, 4, 10, 21, 30),
    ),
}


def list_onboarding_tasks() -> list[OnboardingTask]:
    return list(_TASKS.values())


def get_onboarding_task(key: str) -> OnboardingTask | None:
    return _TASKS.get(key)


# --- Due-nudge computation ------------------------------------------------


@dataclass
class DueNudge:
    task_key: str
    task_label: str
    day_offset: int
    marker: str
    channels: tuple[str, ...]

    def as_dict(self) -> dict:
        return {
            "task_key": self.task_key,
            "task_label": self.task_label,
            "day_offset": self.day_offset,
            "marker": self.marker,
            "channels": list(self.channels),
        }


@dataclass
class NudgeBatch:
    school_id: int
    today: date_type
    days_since_signup: int
    due: list[DueNudge] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "school_id": self.school_id,
            "today": self.today.isoformat(),
            "days_since_signup": self.days_since_signup,
            "due": [d.as_dict() for d in self.due],
        }


def compute_due_nudges(
    *,
    school_id: int,
    signup_date: date_type,
    today: date_type,
    completed_task_keys: set[str] | list[str] | tuple[str, ...] | None,
    already_sent_markers: set[str] | list[str] | tuple[str, ...] | None,
) -> NudgeBatch:
    """Pure function: given task progress + send-history, return today's nudges."""
    completed = set(completed_task_keys or [])
    sent = set(already_sent_markers or [])
    days_since = (today - signup_date).days
    batch = NudgeBatch(
        school_id=school_id, today=today, days_since_signup=days_since,
    )
    if days_since < 0:
        return batch

    for task in _TASKS.values():
        if task.key in completed:
            continue
        for offset in task.nudge_day_offsets:
            if offset > days_since:
                continue
            marker = f"{task.key}:{offset}"
            if marker in sent:
                continue
            # Only fire the latest-overdue nudge for each task (don't spam
            # all earlier ones if the school was inactive over a weekend).
            batch.due.append(
                DueNudge(
                    task_key=task.key,
                    task_label=task.label,
                    day_offset=offset,
                    marker=marker,
                    channels=task.channels,
                )
            )
    # Per task, keep only the highest day_offset that's still due.
    by_task: dict[str, DueNudge] = {}
    for n in batch.due:
        prev = by_task.get(n.task_key)
        if prev is None or n.day_offset > prev.day_offset:
            by_task[n.task_key] = n
    batch.due = sorted(by_task.values(), key=lambda d: (d.day_offset, d.task_key))
    return batch


def record_nudge_sent(
    *,
    school_settings: dict[str, Any] | None,
    marker: str,
    cap: int = 200,
) -> dict[str, Any]:
    settings = dict(school_settings or {})
    bucket = dict(settings.get("customersuccess") or {})
    sent = list(bucket.get("nudges_sent") or [])
    if marker not in sent:
        sent.append(marker)
    if len(sent) > cap:
        sent = sent[-cap:]
    bucket["nudges_sent"] = sent
    settings["customersuccess"] = bucket
    return settings


def get_sent_markers(school_settings: dict[str, Any] | None) -> set[str]:
    bucket = (school_settings or {}).get("customersuccess") or {}
    return set(bucket.get("nudges_sent") or [])
