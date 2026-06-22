"""Copilot rail "Pending / Due" quickstats (GAP-1).

The copilot rail (``templates/partials/cockpit/_ai_copilot_rail.html``) renders a
four-tile quickstat strip: Msg, Alerts, **Pending**, **Due**. The first two are
wired (messages / notifications unread counts), but ``copilot_pending_approvals_count``
and ``copilot_due_today_count`` were *dead bindings* — referenced in the template
yet never populated, so they always rendered ``0``.

This module computes those two counts for the signed-in user and is called once
from the shared site-settings context processor. It is built to be safe on the
hot path (every authenticated request renders the rail):

* **Cached** — the whole result is cached per ``(user, school)`` for
  :data:`QUICKSTATS_CACHE_TTL_SECONDS`, so the queries run at most once a minute
  per user, not once per page.
* **Failure-isolated** — any import / DB error yields zeros and resets the
  (possibly aborted) connection state, exactly like the surrounding context
  processor; the rail must never 500 a page.
* **Honest + un-inflated** — "Pending" counts only items genuinely awaiting *this*
  user's action (leave requests assigned to them as approver; for staff, the
  school's pending grade-approval queue + announcements awaiting approval). "Due"
  counts unsettled invoices dated today within the user's own scope (their
  school for staff; their wards for a guardian; their own for a student).
* **Tenant-scoped** — every query is bound to the request's school (or to the
  user's own relation graph), never cross-tenant.
"""

from __future__ import annotations

import logging
from typing import Dict

from django.db import DatabaseError, connection, transaction
from django.utils import timezone

logger = logging.getLogger(__name__)

#: Keys returned (and merged into the template context). Kept as constants so the
#: template binding and the producer can never silently drift apart.
PENDING_KEY = "copilot_pending_approvals_count"
DUE_KEY = "copilot_due_today_count"

#: Short cache TTL — the rail tolerates a slightly stale count, and this bounds
#: the cost of the underlying COUNT queries to once per user per minute.
QUICKSTATS_CACHE_TTL_SECONDS = 60

_ZERO: Dict[str, int] = {PENDING_KEY: 0, DUE_KEY: 0}

#: Invoice statuses that still owe money (exclude DRAFT / PAID / VOID).
_UNSETTLED_INVOICE_STATUSES = ("ISSUED", "PARTIAL", "OVERDUE")


def _reset_db_state() -> None:
    """Roll back a broken transaction after a handled DB error (mirrors the
    context processor's helper so a guarded failure here can't poison the rest of
    the request)."""
    try:
        if connection.in_atomic_block:
            transaction.set_rollback(False)
        else:
            connection.rollback()
    except (DatabaseError, RuntimeError):
        pass


def _is_staff_like(user) -> bool:
    """True for everyone who works at the school (not a student, not a guardian).

    Keyed off the role enum, never bare literals, so it tracks ``User.Role``.
    """
    try:
        from apps.accounts.models import User

        role = getattr(user, "role", None)
        return role not in (User.Role.STUDENT, User.Role.PARENT)
    except Exception:  # noqa: BLE001 — role resolution must never break the rail
        return False


def _pending_approvals_for(user, school) -> int:
    """Count items genuinely awaiting this user's approval action.

    * Leave requests where the user is the designated ``approver`` and the
      request is still ``PENDING`` (a direct, un-ambiguous assignment).
    * For staff only, the school's grade-approval queue (``PENDING`` /
      ``UNDER_REVIEW``) and announcements awaiting approval — both are
      staff-actionable surfaces, so a student / guardian never sees them.
    """
    total = 0

    # Leave requests assigned directly to this user as approver.
    try:
        from apps.people.models import TeacherLeaveRequest

        total += TeacherLeaveRequest.objects.filter(
            approver=user, status=TeacherLeaveRequest.Status.PENDING
        ).count()
    except DatabaseError:
        _reset_db_state()
    except Exception:  # noqa: BLE001 — never break the rail on a missing relation
        logger.debug("copilot quickstats: leave-pending count failed", exc_info=True)

    if not _is_staff_like(user) or school is None:
        return total

    # School's pending grade-approval queue (no per-reviewer assignment exists, so
    # it is a shared staff queue). Scoped to the school via the teacher relation.
    try:
        from apps.evals.models import GradeApprovalRequest

        # tenant-isolation-allow: scoped-via-teacher-school-to-request-school
        total += GradeApprovalRequest.objects.filter(
            teacher__school=school,
            status__in=(
                GradeApprovalRequest.Status.PENDING,
                GradeApprovalRequest.Status.UNDER_REVIEW,
            ),
        ).count()
    except DatabaseError:
        _reset_db_state()
    except Exception:  # noqa: BLE001
        logger.debug("copilot quickstats: grade-approval count failed", exc_info=True)

    # Announcements awaiting approval in this school.
    try:
        from apps.communication.models import Announcement

        # tenant-isolation-allow: explicit-school-filter-on-announcement-row
        total += Announcement.objects.filter(
            school=school, status=Announcement.Status.PENDING_APPROVAL
        ).count()
    except DatabaseError:
        _reset_db_state()
    except Exception:  # noqa: BLE001
        logger.debug("copilot quickstats: announcement-pending count failed", exc_info=True)

    return total


def _due_today_for(user, school) -> int:
    """Count unsettled invoices dated today within the user's own scope.

    * Staff → every unsettled invoice in their school due today.
    * Guardian → unsettled invoices due today for any of their wards.
    * Student → their own unsettled invoices due today.
    """
    try:
        from apps.finance.models import Invoice

        today = timezone.localdate()
        # tenant-isolation-allow: base-qs-always-narrowed-by-school-or-user-before-eval
        base = Invoice.objects.filter(
            due_date=today, status__in=_UNSETTLED_INVOICE_STATUSES
        )

        if _is_staff_like(user):
            if school is None:
                return 0
            # tenant-isolation-allow: explicit-school-filter-on-invoice-row
            return base.filter(school=school).count()

        # Guardian: invoices for their linked wards.
        from apps.accounts.models import User

        if getattr(user, "role", None) == User.Role.PARENT:
            # tenant-isolation-allow: scoped-through-guardian-link-to-this-user
            return base.filter(
                student__guardian_links__guardian_user=user
            ).distinct().count()

        # Student: their own invoices.
        # tenant-isolation-allow: scoped-through-student-profile-to-this-user
        return base.filter(student__user=user).count()
    except DatabaseError:
        _reset_db_state()
        return 0
    except Exception:  # noqa: BLE001 — never break the rail
        logger.debug("copilot quickstats: due-today count failed", exc_info=True)
        return 0


def build_copilot_quickstats(request) -> Dict[str, int]:
    """Return ``{pending, due}`` counts for the rail, cached + failure-isolated.

    Always returns both keys (zeros for anonymous users or on any error), so the
    template binding is never missing.
    """
    user = getattr(request, "user", None)
    if not user or not getattr(user, "is_authenticated", False) or not getattr(user, "pk", None):
        return dict(_ZERO)

    school = getattr(request, "school", None)
    school_id = getattr(school, "pk", None)

    cache_key = f"copilot_quickstats:{user.pk}:{school_id or 0}"
    try:
        from django.core.cache import cache

        cached = cache.get(cache_key)
        if cached is not None:
            return cached
    except Exception:  # noqa: BLE001 — cache outage must not break the rail
        cache = None

    result = {
        PENDING_KEY: _pending_approvals_for(user, school),
        DUE_KEY: _due_today_for(user, school),
    }

    if cache is not None:
        try:
            cache.set(cache_key, result, QUICKSTATS_CACHE_TTL_SECONDS)
        except Exception:  # noqa: BLE001
            pass
    return result


__all__ = ["build_copilot_quickstats", "PENDING_KEY", "DUE_KEY"]
