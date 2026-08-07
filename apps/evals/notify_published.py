"""Grade direct-post notification emitter (MED-6 / Phase 4).

The audit found that ``grade.published`` is emitted ONLY by the approval path
(:func:`apps.evals.approval.try_emit_grade_published_event`, fired when a
:class:`~apps.evals.models.GradeApprovalRequest` reaches ``APPROVED`` — and via the
*internal* :mod:`apps.events` bus, not the notification router). A grade saved
**directly** by a teacher (no approval workflow) therefore notified nobody.

This module closes that gap. When a teacher saves marks directly — the path that
does NOT route through ``submit_for_approval`` — the view calls
:func:`notify_grades_published_direct`, which fans a ``grade.published`` event out
to each affected student's own user **and** their guardians via the Phase-3
:func:`apps.communication.dispatch.dispatch_event` router (the single
event → preference → channel path; no hand-rolled channel logic here).

Design rules honoured:

* **No double-fire** — this is invoked only on the *direct* save branch of the
  marks view; the approval branch returns before reaching it, so an approved batch
  (which already emits ``grade.published`` via the event bus) never re-notifies
  here.
* **PII-safe logging** — on failure we log the *exception type only*, never a
  student name or score (there is a pii-logging-smell gate).
* **Failure-isolated** — the whole fan-out is wrapped so a notification failure can
  never break the grade save; each recipient dispatch is additionally isolated.
* **Transaction-safe** — the fan-out is deferred with
  :func:`~django.db.transaction.on_commit`, so it runs only after the grade rows
  are committed and outside the saving transaction.
* **Tenant-scoped** — ``school`` is threaded through to ``dispatch_event`` and the
  guardian/student lookups are scoped to the affected students.
"""

from __future__ import annotations

import logging
from typing import Any, Iterable, List

from django.db import transaction

logger = logging.getLogger(__name__)

#: Event key (already routed to Category.GRADES in dispatch.EVENT_CATEGORY_MAP).
GRADE_PUBLISHED_EVENT = "grade.published"

#: Subject-name preview cap so a long subject label can't bloat the in-app/push
#: payload (named, not a literal at the call site).
SUBJECT_PREVIEW_CHARS = 80  # magic-number-allow: notification title subject-label cap


def _subject_label(subject_assignment: Any) -> str:
    """Best-effort human label for the subject, capped + never raising."""
    try:
        subject = getattr(subject_assignment, "subject", None)
        label = (getattr(subject, "name", "") or str(subject_assignment) or "").strip()
    except Exception:  # noqa: BLE001 — label resolution must never break the notify
        label = ""
    if not label:
        return "a subject"
    return label[:SUBJECT_PREVIEW_CHARS]


def _results_link() -> str:
    """Best-effort student results URL → ``""`` if not reversible."""
    try:
        from django.urls import reverse

        return reverse("reports:student_results")
    except Exception:  # noqa: BLE001 — missing/renamed URL must not break the notify
        return ""


def _recipient_users_for_student(student: Any) -> List[Any]:
    """Resolve the user(s) to notify for one student: the student + guardians.

    Returns the student's own ``user`` (when linked) plus every guardian user who
    is allowed to view results. The guardian lookup is scoped to *this* student
    (the relation is already student-scoped), so no cross-tenant leakage is
    possible. Never raises — a bad relation just yields fewer recipients.
    """
    recipients: List[Any] = []
    try:
        student_user = getattr(student, "user", None)
        if student_user is not None and getattr(student_user, "pk", None):
            recipients.append(student_user)
    except Exception:  # noqa: BLE001 — student-user resolution never breaks notify
        logger.debug("grade.published student-user resolve failed", exc_info=True)

    try:
        links = getattr(student, "guardian_links", None)
        if links is not None:
            # tenant-isolation-allow: relation-is-student-scoped-already
            for link in links.filter(
                guardian_user__isnull=False, can_view_results=True
            ).select_related("guardian_user"):
                guardian_user = getattr(link, "guardian_user", None)
                if guardian_user is not None and getattr(guardian_user, "pk", None):
                    recipients.append(guardian_user)
    except Exception:  # noqa: BLE001 — guardian resolution never breaks notify
        logger.debug("grade.published guardian resolve failed", exc_info=True)

    # De-dupe (a teacher who is also a guardian could appear twice).
    seen: set = set()
    unique: List[Any] = []
    for user in recipients:
        pk = getattr(user, "pk", None)
        if pk in seen:
            continue
        seen.add(pk)
        unique.append(user)
    return unique


def notify_grades_published_direct(
    *,
    students: Iterable[Any],
    subject_assignment: Any,
    school: Any = None,
) -> None:
    """Fan a ``grade.published`` notification to each student + guardians.

    Called from the *direct* marks-save branch (no approval workflow). Wrapped so a
    notification failure can never break the grade write, and deferred to
    ``on_commit`` so it sees committed grade rows.

    Parameters
    ----------
    students:
        The :class:`~apps.people.models.StudentProfile` rows whose grades were just
        saved directly.
    subject_assignment:
        The :class:`~apps.academics.models.SubjectAssignment` for these grades
        (used only to build the human-readable title — no PII).
    school:
        Tenant scope, threaded through to the router.
    """
    try:
        # Snapshot the students up-front so the deferred closure doesn't depend on a
        # lazily-evaluated queryset that may be exhausted/re-queried post-commit.
        student_list = [s for s in (students or []) if s is not None]
        if not student_list:
            return

        subject_label = _subject_label(subject_assignment)
        link = _results_link()
        # Render in the tenant's language so a francophone school's parents get a
        # French notification (strings resolve from the gettext catalog).
        from django.utils import translation
        from django.utils.translation import gettext as _

        _locale = ""
        try:
            from apps.siteconfig.tenant_config import get_tenant_locale

            _loc = get_tenant_locale(school=school)
            _locale = (_loc.get("default_language") or _loc.get("locale") or "").strip()
        except Exception:  # noqa: BLE001 — locale lookup must not break notify
            _locale = ""
        with translation.override(_locale or None):
            title = _("New grades published")
            message = _("New grades have been published for %(subject)s.") % {
                "subject": subject_label
            }

        def _dispatch() -> None:
            from apps.communication.dispatch import dispatch_event

            context = {
                "title": title,
                "message": message,
                "link": link,
                "severity": "INFO",
            }
            for student in student_list:
                for recipient in _recipient_users_for_student(student):
                    try:
                        dispatch_event(
                            GRADE_PUBLISHED_EVENT,
                            recipient=recipient,
                            context=context,
                            school=school,
                        )
                    except Exception as exc:  # noqa: BLE001 — never break on-commit
                        # PII-safe: error *type* only, never student/score.
                        logger.warning(
                            "grade.published dispatch failed err=%s",
                            type(exc).__name__,
                        )

        transaction.on_commit(_dispatch)

    except Exception as exc:  # noqa: BLE001 — a notification must never break save()
        # PII-safe: error *type* only, never student/score.
        logger.warning(
            "grade.published direct-notify failed err=%s",
            type(exc).__name__,
        )


__all__ = ["notify_grades_published_direct", "GRADE_PUBLISHED_EVENT"]
