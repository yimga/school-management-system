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

Destinations are ``url_name``, never a literal path
---------------------------------------------------
Every chip here used to carry a hardcoded ``href``. Six of the ten chips
that actually render — this strip is in ``portal_base.html``, so it is on
every portal page for every persona — returned 404 on a real tenant host.
The whole student strip was dead.

The reason they survived is worth stating, because it will recur:
``UrlConfSwitcherMiddleware`` gives a local/dev host ``config.urls``, which
mounts the full URL surface, while a school on a subdomain gets
``config.tenant_urls``, which does not. ``/parent/finance/`` resolves on the
first and 404s on the second. A literal path never raises, so nothing ever
noticed — ``reverse()`` on a moved route does.

``test_action_hub_destinations_resolve`` renders every persona's hub under
``config.tenant_urls`` and clicks every chip. Add chips with ``url_name``.
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
    url_name: str = ""      # preferred: reverse() fails loudly when a route moves
    href: str = ""          # literal path — see the warning in __post_init__
    query: str = ""         # querystring appended to the reversed url_name
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
        """Every chip the assembler decided to show.

        This used to drop anything with ``count == 0`` unless it was severity
        ``info``, on the theory that a zero-count chip is noise. It isn't: a
        count is not how most alerts are expressed. "Storage nearing capacity",
        "Transcript hold active" and "Pay family balance" are boolean or
        amount-driven states with no count at all, and the filter deleted all
        three — a danger-severity transcript hold silently removed from the one
        strip whose job is to surface it.

        There is nothing to second-guess here. Every assembler below already
        gates each append on the condition that makes the chip worth showing
        (``if overdue_homework_review > 0``, ``if records_hold_active``), so a
        chip that reached this tuple has already earned its place. The count is
        a badge on the chip, not the reason for it.
        """
        return tuple(self.actions)


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
            url_name="finance:invoices",
            query="status=OVERDUE",
        ))
    if storage_warning:
        actions.append(HubAction(
            key="storage.nearing_cap",
            label="Storage nearing capacity",
            severity="warning",
            icon="bi-hdd",
            url_name="siteconfig:billing_plan_readonly",
            query="focus=storage",
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
            url_name="portal:take_student_attendance",
            helper_text="One-tap whole-class mark + exceptions.",
        ))
    if overdue_homework_review > 0:
        actions.append(HubAction(
            key="homework.review",
            label="Homework submissions to grade",
            count=overdue_homework_review,
            severity="info",
            icon="bi-journal-text",
            url_name="portal:teacher_gradebook",
        ))
    if pending_messages > 0:
        actions.append(HubAction(
            key="messages.pending",
            label="Unread parent messages",
            count=pending_messages,
            severity="info",
            icon="bi-chat-square-text",
            url_name="accounts:user_messages",
        ))
    if classes_today > 0 and attendance_pending_classes == 0:
        actions.append(HubAction(
            key="day.clear",
            label="All today's attendance is in",
            severity="success",
            icon="bi-check2-circle",
            url_name="portal:teacher_dashboard_alias",
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
            url_name="accounts:user_messages",
        ))
    if upcoming_events > 0:
        actions.append(HubAction(
            key="events.upcoming",
            label="Upcoming school events",
            count=upcoming_events,
            severity="info",
            icon="bi-calendar-event",
            url_name="portal:unified_calendar",
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
            url_name="portal:student_assignments",
        ))
    if upcoming_exams > 0:
        actions.append(HubAction(
            key="exams.upcoming",
            label="Upcoming assessments",
            count=upcoming_exams,
            severity="info",
            icon="bi-pencil-square",
            url_name="portal:student_portal_grades",
        ))
    if unread_messages > 0:
        actions.append(HubAction(
            key="messages.unread",
            label="Unread school messages",
            count=unread_messages,
            severity="info",
            icon="bi-chat-square-text",
            url_name="accounts:user_messages",
        ))
    return ActionHub(persona=PERSONA_STUDENT, actions=_sort_actions(actions))


def empty_hub(persona: str = PERSONA_ANY) -> ActionHub:
    """A no-action hub — used as the default fallback."""
    return ActionHub(persona=persona, actions=())


def _baseline_navigation_actions(persona: str) -> tuple[HubAction, ...]:
    """Always-on thumb targets when no operational counts are present."""
    if persona == PERSONA_TEACHER:
        return (
            HubAction(
                key="nav.attendance",
                label="Take attendance",
                severity="info",
                icon="bi-clipboard-check",
                url_name="evals:teacher_dashboard",
            ),
            HubAction(
                key="nav.marks",
                label="Enter marks",
                severity="info",
                icon="bi-journal-text",
                url_name="evals:teacher_marks_entry",
            ),
            HubAction(
                key="nav.messages",
                label="Messages",
                severity="info",
                icon="bi-chat-square-text",
                url_name="accounts:user_messages",
            ),
        )
    if persona == PERSONA_PARENT:
        return (
            HubAction(
                key="nav.finance",
                label="Family finance",
                severity="info",
                icon="bi-receipt",
                url_name="portal:parent_finance",
            ),
            HubAction(
                key="nav.messages",
                label="School messages",
                severity="info",
                icon="bi-chat-square-text",
                url_name="accounts:user_messages",
            ),
            HubAction(
                key="nav.calendar",
                label="Calendar",
                severity="info",
                icon="bi-calendar-event",
                url_name="portal:unified_calendar",
            ),
        )
    if persona == PERSONA_STUDENT:
        return (
            HubAction(
                key="nav.homework",
                label="Homework",
                severity="info",
                icon="bi-journal-arrow-up",
                url_name="portal:student_assignments",
            ),
            HubAction(
                key="nav.learning",
                label="Learning home",
                severity="info",
                icon="bi-mortarboard",
                url_name="portal:student_portal_grades",
            ),
        )
    if persona == PERSONA_TENANT_ADMIN:
        return (
            HubAction(
                key="nav.backend",
                label="School workspace",
                severity="info",
                icon="bi-grid",
                url_name="accounts:backend_dashboard",
            ),
            HubAction(
                key="nav.people",
                label="People directory",
                severity="info",
                icon="bi-people",
                url_name="accounts:backend_student_list",
            ),
        )
    return ()


def resolve_hub_for_audience(audience: str, **counts) -> ActionHub:
    """Build persona hub; merge baseline navigation when no urgent chips exist."""
    builders = {
        "teacher": build_teacher_hub,
        "parent": build_parent_hub,
        "student": build_student_hub,
        "tenant_admin": build_tenant_admin_hub,
        "admin": build_tenant_admin_hub,
    }
    persona_map = {
        "teacher": PERSONA_TEACHER,
        "parent": PERSONA_PARENT,
        "student": PERSONA_STUDENT,
        "tenant_admin": PERSONA_TENANT_ADMIN,
        "admin": PERSONA_TENANT_ADMIN,
    }
    persona = persona_map.get(audience, PERSONA_ANY)
    builder = builders.get(audience)
    hub = builder(**counts) if builder else empty_hub(persona)
    if hub.non_empty_actions:
        return hub
    baseline = _baseline_navigation_actions(persona)
    if baseline:
        return ActionHub(persona=persona, actions=_sort_actions(baseline))
    return hub
