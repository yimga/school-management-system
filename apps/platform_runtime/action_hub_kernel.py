"""Wave U (v3.99.0 — 2026-05-27) — Smart Action Hub composition kernel.

The Action Hub is the top-of-page strip that surfaces every actionable
state a persona currently has: open admission queue, urgent DSL inbox
items, overdue invoices, frozen-account warnings, etc.

Each hub item is a ``HubAction``: a persona-scoped state token, a primary
smart-link target, and a count/severity. Templates render the strip via
``{% render_action_hub persona=... %}``.

The kernel is pure-Python and composition-only — it doesn't read the DB.
Callers (the view layer) collect counts via existing kernels (DSL inbox
count, admissions queue count, overdue invoice aggregate, etc.) and pass
the numbers in. This keeps the kernel ``SimpleTestCase``-friendly.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


PERSONA_ANY = "any"
PERSONA_OPERATOR = "operator"
PERSONA_TENANT_ADMIN = "tenant_admin"
PERSONA_TEACHER = "teacher"
PERSONA_PARENT = "parent"
PERSONA_STUDENT = "student"
PERSONA_STAFF = "staff"


@dataclass(frozen=True)
class HubAction:
    """A single action chip in the top-of-page Action Hub."""

    key: str
    label: str
    count: int = 0
    severity: str = "info"   # info | warning | danger | success
    icon: str = "bi-stars"
    url_name: str = ""
    href: str = ""
    state_token: str = ""   # optional smart_links_kernel state to use instead
    helper_text: str = ""

    def __post_init__(self) -> None:
        if not self.label:
            raise ValueError("HubAction.label is required")
        if self.severity not in {"info", "warning", "danger", "success"}:
            raise ValueError(f"invalid severity {self.severity!r}")
        if self.count < 0:
            raise ValueError("HubAction.count cannot be negative")
        if not (self.url_name or self.href or self.state_token):
            raise ValueError(
                f"HubAction {self.label!r}: set url_name, href, or state_token",
            )


@dataclass(frozen=True)
class ActionHub:
    """Composed strip of HubAction chips for a given persona."""

    persona: str
    actions: tuple[HubAction, ...]

    @property
    def has_urgent(self) -> bool:
        return any(a.severity == "danger" and a.count > 0 for a in self.actions)

    @property
    def total_count(self) -> int:
        return sum(a.count for a in self.actions)

    @property
    def non_empty_actions(self) -> tuple[HubAction, ...]:
        """Filter out zero-count chips so dashboards don't render noise."""
        return tuple(a for a in self.actions if a.count > 0 or a.severity == "info")


_SEVERITY_RANK = {"danger": 0, "warning": 1, "info": 2, "success": 3}


def _sort_actions(actions: Iterable[HubAction]) -> tuple[HubAction, ...]:
    """Stable sort: most urgent + highest-count first."""
    return tuple(
        sorted(
            actions,
            key=lambda a: (_SEVERITY_RANK.get(a.severity, 9), -a.count, a.key),
        ),
    )


# --- Per-persona action assemblers ----------------------------------------


def build_tenant_admin_hub(
    *,
    pending_admissions: int = 0,
    open_safeguarding: int = 0,
    urgent_dsl_inbox: int = 0,
    overdue_invoices: int = 0,
    storage_warning: bool = False,
) -> ActionHub:
    """Top-of-page Action Hub for a tenant admin."""
    actions: list[HubAction] = []
    if urgent_dsl_inbox > 0:
        actions.append(HubAction(
            key="safeguarding.urgent",
            label="Safeguarding — DSL action required",
            count=urgent_dsl_inbox,
            severity="danger",
            icon="bi-shield-exclamation",
            state_token="safeguarding.concern_open",
            helper_text="KCSIE 2026 SLA — review before end of day.",
        ))
    if open_safeguarding > 0:
        actions.append(HubAction(
            key="safeguarding.open",
            label="Open safeguarding concerns",
            count=open_safeguarding,
            severity="warning",
            icon="bi-shield",
            state_token="safeguarding.concern_open",
        ))
    if pending_admissions > 0:
        actions.append(HubAction(
            key="admissions.pending",
            label="Admissions awaiting review",
            count=pending_admissions,
            severity="warning",
            icon="bi-inbox",
            state_token="admission.pending_review",
        ))
    if overdue_invoices > 0:
        actions.append(HubAction(
            key="finance.overdue",
            label="Family invoices overdue",
            count=overdue_invoices,
            severity="warning",
            icon="bi-receipt",
            href="/school/finance/?filter=overdue",
        ))
    if storage_warning:
        actions.append(HubAction(
            key="storage.nearing_cap",
            label="Storage nearing capacity",
            severity="warning",
            icon="bi-hdd",
            href="/school/settings/storage/",
            helper_text="Free up space or upgrade before write-blocking kicks in.",
        ))
    return ActionHub(persona=PERSONA_TENANT_ADMIN, actions=_sort_actions(actions))


def build_teacher_hub(
    *,
    classes_today: int = 0,
    attendance_pending_classes: int = 0,
    overdue_homework_review: int = 0,
    pending_messages: int = 0,
) -> ActionHub:
    """Top-of-page Action Hub for a teacher."""
    actions: list[HubAction] = []
    if attendance_pending_classes > 0:
        actions.append(HubAction(
            key="attendance.pending",
            label="Classes awaiting attendance",
            count=attendance_pending_classes,
            severity="warning",
            icon="bi-clipboard-check",
            href="/teacher/attendance/today/",
            helper_text="One-tap whole-class mark + exceptions.",
        ))
    if overdue_homework_review > 0:
        actions.append(HubAction(
            key="homework.review",
            label="Homework submissions to grade",
            count=overdue_homework_review,
            severity="info",
            icon="bi-journal-text",
            href="/teacher/homework/?filter=needs_grade",
        ))
    if pending_messages > 0:
        actions.append(HubAction(
            key="messages.pending",
            label="Unread parent messages",
            count=pending_messages,
            severity="info",
            icon="bi-chat-square-text",
            href="/teacher/messages/",
        ))
    if classes_today > 0 and attendance_pending_classes == 0:
        actions.append(HubAction(
            key="day.clear",
            label="All today's attendance is in",
            severity="success",
            icon="bi-check2-circle",
            href="/teacher/dashboard/",
        ))
    return ActionHub(persona=PERSONA_TEACHER, actions=_sort_actions(actions))


def build_parent_hub(
    *,
    outstanding_balance_currency: str = "",
    outstanding_balance_amount: str = "",  # str-decimal (no float for money)
    unread_messages: int = 0,
    upcoming_events: int = 0,
    records_hold_active: bool = False,
) -> ActionHub:
    """Top-of-page Action Hub for a parent."""
    actions: list[HubAction] = []
    if outstanding_balance_amount and outstanding_balance_amount != "0":
        label = "Pay family balance"
        if outstanding_balance_currency:
            label = (
                f"Pay {outstanding_balance_currency}{outstanding_balance_amount} "
                "family balance"
            )
        actions.append(HubAction(
            key="finance.balance",
            label=label,
            severity="warning",
            icon="bi-credit-card",
            state_token="invoice.overdue",
            helper_text="One checkout covers every linked learner.",
        ))
    if records_hold_active:
        actions.append(HubAction(
            key="records.hold",
            label="Transcript hold active",
            severity="danger",
            icon="bi-folder-x",
            state_token="records.hold_active",
        ))
    if unread_messages > 0:
        actions.append(HubAction(
            key="messages.unread",
            label="Unread school messages",
            count=unread_messages,
            severity="info",
            icon="bi-chat-square-text",
            href="/portal/messages/",
        ))
    if upcoming_events > 0:
        actions.append(HubAction(
            key="events.upcoming",
            label="Upcoming school events",
            count=upcoming_events,
            severity="info",
            icon="bi-calendar-event",
            href="/portal/calendar/",
        ))
    return ActionHub(persona=PERSONA_PARENT, actions=_sort_actions(actions))


def build_student_hub(
    *,
    homework_due_count: int = 0,
    upcoming_exams: int = 0,
    unread_messages: int = 0,
) -> ActionHub:
    """Top-of-page Action Hub for a student."""
    actions: list[HubAction] = []
    if homework_due_count > 0:
        actions.append(HubAction(
            key="homework.due",
            label="Homework due",
            count=homework_due_count,
            severity="warning",
            icon="bi-journal-arrow-up",
            href="/student/homework/",
        ))
    if upcoming_exams > 0:
        actions.append(HubAction(
            key="exams.upcoming",
            label="Upcoming assessments",
            count=upcoming_exams,
            severity="info",
            icon="bi-pencil-square",
            href="/student/assessments/",
        ))
    if unread_messages > 0:
        actions.append(HubAction(
            key="messages.unread",
            label="Unread school messages",
            count=unread_messages,
            severity="info",
            icon="bi-chat-square-text",
            href="/portal/messages/",
        ))
    return ActionHub(persona=PERSONA_STUDENT, actions=_sort_actions(actions))


def empty_hub(persona: str = PERSONA_ANY) -> ActionHub:
    """A no-action hub — used as the default fallback."""
    return ActionHub(persona=persona, actions=())
