"""Term-results-published notification (closes the hybrid-visibility loop).

The audit found that the per-grade ``grade.published`` event fires when a teacher
*enters* marks (:mod:`apps.evals.notify_published`), but the **term-publish
milestone** — an admin flipping :class:`~apps.reports.models.TermPublishStatus` to
``is_published=True`` in the report-publish view — notified **nobody**. That milestone
is exactly what gates the ``published`` mode of ``student_results_visibility``
(:func:`apps.portal.student_results_visibility.resolve_student_grade_dashboard_access`):
in that mode a student/guardian sees results *only after* the term is published, so the
moment it happens is the one moment worth telling them about.

This module closes that gap. The report-publish view calls
:func:`notify_term_results_published` after the publish rows are written; it fans the
already-routed ``grade.published`` event (term scope) out to each affected student's own
user **and** their results-permitted guardians via the Phase-3
:func:`apps.communication.dispatch.dispatch_event` router (the single
event → preference → channel path — no hand-rolled channel logic here).

Design rules honoured (mirrors :mod:`apps.evals.notify_published`):

* **Policy-gated** — when ``student_results_visibility`` is ``off`` there are no
  results to announce, so the whole fan-out is skipped. ``entered`` and ``published``
  both notify (the term-publish milestone is meaningful in either mode).
* **Reuses the routed event** — ``grade.published`` is already mapped to
  ``Category.GRADES`` in :data:`apps.communication.dispatch.EVENT_CATEGORY_MAP`, so the
  recipient's existing GRADES channel preference governs delivery and no new event key
  has to be registered.
* **PII-safe logging** — on failure we log the *exception type only*, never a student
  name or score (there is a pii-logging-smell gate).
* **Failure-isolated** — a notification failure can never break the publish write; each
  recipient dispatch is additionally isolated.
* **Transaction-safe** — deferred with :func:`django.db.transaction.on_commit`, so it
  runs only after the publish rows are committed and outside the publish transaction.
* **Tenant-scoped** — ``school`` is threaded through to ``dispatch_event`` and the
  student/guardian lookups are scoped to the published school + classrooms.
"""

from __future__ import annotations

import logging
from typing import Any, Iterable, List, Optional

from django.db import transaction

from apps.evals.notify_published import (
    GRADE_PUBLISHED_EVENT,
    _recipient_users_for_student,
)
from apps.portal.student_results_visibility import (
    STUDENT_RESULTS_VISIBILITY_OFF,
    get_student_results_visibility_from_site,
    normalize_student_results_visibility,
)

logger = logging.getLogger(__name__)

#: Term-label preview cap so a long term name can't bloat the in-app/push payload
#: (named, not a literal at the call site).
TERM_PREVIEW_CHARS = 80  # magic-number-allow: notification title term-label cap


def _term_label(term: Any) -> str:
    """Best-effort human label for the term, capped + never raising."""
    try:
        label = (
            getattr(term, "label", "")
            or getattr(term, "name", "")
            or str(term or "")
        ).strip()
    except Exception:  # noqa: BLE001 — label resolution must never break the notify
        label = ""
    if not label:
        return "this term"
    return label[:TERM_PREVIEW_CHARS]


#: Route names tried, in order, for the "your results are ready" deep link.
#: This used to reverse ``reports:student_results``, a name that exists in NO
#: urlconf, so ``_results_link`` returned ``""`` every single time and every
#: term-publish notification shipped with no way to reach the results. (The
#: bulk-share notification had the mirror-image bug: a hardcoded ``"/reports/"``,
#: which resolves to nothing on ``config/tenant_urls.py`` — it is only a route on
#: the dev-only ``config/urls.py``, where it is the public MARKETING page, which
#: is exactly why it looked fine locally.) ``portal`` IS mounted on the tenant
#: host, so these names resolve for a real school.
STUDENT_RESULTS_ROUTE_NAMES = (
    "portal:student_portal_grades",
    "portal:parent_dashboard",
)


def student_results_link() -> str:
    """The URL a "results are ready" notification should open — ``""`` if none."""
    from django.urls import reverse

    for name in STUDENT_RESULTS_ROUTE_NAMES:
        try:
            return reverse(name)
        except Exception:  # noqa: BLE001 — missing/renamed URL must not break the notify
            continue
    return ""


def _results_link() -> str:
    """Backwards-compatible alias for :func:`student_results_link`."""
    return student_results_link()


def _students_for_scope(
    *, school: Any, year: Any, classroom_ids: Optional[Iterable[Any]]
) -> List[Any]:
    """Resolve the active students whose term was just published.

    ``classroom_ids`` empty/None means a whole-school publish → every active student
    in the year. Otherwise it is the set of published classroom ids. Never raises — a
    bad scope just yields fewer recipients.
    """
    try:
        from apps.people.models import StudentProfile

        qs = StudentProfile.objects.filter(
            school=school,
            academic_year=year,
            is_active=True,
            deleted_at__isnull=True,
        )
        ids = [c for c in (classroom_ids or []) if c not in (None, "")]
        if ids:
            qs = qs.filter(classroom_id__in=ids)
        return list(qs.select_related("user"))
    except Exception:  # noqa: BLE001 — student resolution never breaks the publish
        logger.debug("term.published student resolve failed", exc_info=True)
        return []


def notify_term_results_published(
    *,
    school: Any,
    year: Any,
    term: Any,
    classroom_ids: Optional[Iterable[Any]] = None,
    visibility_mode: Optional[str] = None,
    site: Any = None,
) -> None:
    """Fan a term-publish notification to each affected student + guardians.

    Called from the report-publish view's publish branch. Wrapped so a notification
    failure can never break the publish write, and deferred to ``on_commit`` so it sees
    the committed :class:`~apps.reports.models.TermPublishStatus` rows.

    Parameters
    ----------
    school:
        Tenant scope, threaded through to the router and the student lookup.
    year, term:
        The published :class:`~apps.academics.models.AcademicYear` /
        :class:`~apps.academics.models.Term` (term used only for the human title).
    classroom_ids:
        Published classroom ids; empty/None ⇒ whole-school publish (all active
        students in the year).
    visibility_mode:
        The resolved ``student_results_visibility`` mode. When omitted it is read from
        ``site`` (or the school's effective settings). ``off`` ⇒ no fan-out.
    site:
        Optional pre-resolved effective site settings (avoids a re-resolve).
    """
    try:
        mode = (
            normalize_student_results_visibility(visibility_mode)
            if visibility_mode is not None
            else get_student_results_visibility_from_site(site)
        )
        if mode == STUDENT_RESULTS_VISIBILITY_OFF:
            return

        student_list = _students_for_scope(
            school=school, year=year, classroom_ids=classroom_ids
        )
        if not student_list:
            return

        term_label = _term_label(term)
        link = _results_link()
        title = "Term results published"
        message = f"Your {term_label} results are now available to view."

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
                            "term.published dispatch failed err=%s",
                            type(exc).__name__,
                        )

        transaction.on_commit(_dispatch)

    except Exception as exc:  # noqa: BLE001 — a notification must never break publish
        # PII-safe: error *type* only, never student/score.
        logger.warning(
            "term.published notify failed err=%s",
            type(exc).__name__,
        )


__all__ = ["notify_term_results_published", "student_results_link"]
