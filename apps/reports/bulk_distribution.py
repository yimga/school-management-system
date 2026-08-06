"""Distribute a report-card group to parents/students (online now, or offline-drained).

"Bulk share" is the third verb (after generate + print): tell every family in a
class or specialty that their term report card is ready, through the same routed
``grade.published`` event the per-term publish uses — so the recipient's existing
GRADES channel preference governs delivery and no new channel logic is hand-rolled
here.

This function is the SINGLE distribution path. The console view calls it directly
when online; the offline ``report_batch.distribute`` action's applier calls the
very same function when the edge box drains its queue back to the server. Local
first: a school with no connectivity queues the share and it goes out the moment
the link returns, with no second code path to drift.
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def distribute_report_batch(
    *, school: Any, academic_year: Any, term: Any, classroom: Any = None, specialty: Any = None
) -> dict:
    """Notify each student + results-permitted guardian in a group that cards are ready.

    Returns ``{"ok": True, "students": n, "notified": m}``. Never raises for a
    single recipient's failure — one bad dispatch must not abandon the rest;
    logging is PII-safe (exception type only), matching the publish-notify path.
    """
    from apps.communication.dispatch import dispatch_event
    from apps.evals.notify_published import (
        GRADE_PUBLISHED_EVENT,
        _recipient_users_for_student,
    )
    from apps.reports.distribution_grouping import scoped_student_queryset

    students = list(
        scoped_student_queryset(
            school, academic_year, classroom=classroom, specialty=specialty
        )
    )
    if not students:
        return {"ok": True, "students": 0, "notified": 0}

    term_label = (
        getattr(term, "label", None) or getattr(term, "name", None) or "term"
    )
    context = {
        "title": "Report card ready",
        "message": f"Your {term_label} report card is ready to view.",
        "link": "/reports/",
        "severity": "INFO",
    }

    notified = 0
    for student in students:
        for recipient in _recipient_users_for_student(student):
            try:
                dispatch_event(
                    GRADE_PUBLISHED_EVENT,
                    recipient=recipient,
                    context=context,
                    school=school,
                )
                notified += 1
            except Exception as exc:  # noqa: BLE001 — never abandon the batch on one failure
                logger.warning(
                    "report_batch.distribute dispatch failed err=%s",
                    type(exc).__name__,
                )
    return {"ok": True, "students": len(students), "notified": notified}
