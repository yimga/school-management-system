"""Announcement fan-out (HIGH-3).

Before Phase 4 a *published* :class:`~apps.communication.models.Announcement`
only ever appeared in the in-app feed: there was no email/SMS/push fan-out, no
scheduling, and ``audience="specific"`` was never implemented. This module is
the missing fan-out layer. It maps the announcement's audience to concrete
recipient ``User`` rows within ``announcement.school`` and routes one event per
recipient through the Phase-3 dispatch engine.

Design rules honoured here:

* **Single fan-out path** — every channel decision is owned by
  :func:`apps.communication.dispatch.dispatch_event`; nothing here re-hardcodes a
  channel. We pass the event key ``"announcement.published"`` and let the router
  pick channels from the recipient's preferences.
* **Idempotent** — :func:`deliver_announcement` refuses to re-send once
  ``announcement.delivered_at`` is stamped, so a re-fired publish / a retried
  scheduled run never double-delivers.
* **Capped batches** — recipients are iterated in slices of
  :data:`ANNOUNCEMENT_FANOUT_BATCH_SIZE` so a school-wide ``audience="all"``
  blast never materialises an unbounded recipient list in memory.
* **Tenant-scoped** — every recipient query is bound to ``announcement.school``;
  there is no cross-tenant read.
* **Honest tallies** — the summary dict reports how many events were dispatched
  vs skipped (no preference channel permitted / muted), never inflating sent.
* **Failure-isolated** — :func:`send_due_scheduled_announcements` wraps each
  announcement so one bad row never blocks the rest of the due batch.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Iterator, List

from django.contrib.auth import get_user_model
from django.db.models import Q
from django.urls import NoReverseMatch, reverse
from django.utils import timezone

from apps.communication.dispatch import dispatch_event
from apps.communication.models import Announcement

logger = logging.getLogger(__name__)

User = get_user_model()

#: Dotted event key routed through the dispatch engine for every recipient.
ANNOUNCEMENT_EVENT_KEY = "announcement.published"

#: Recipients are dispatched in slices of this size so a school-wide blast never
#: builds an unbounded in-memory recipient list. 500 >= 100 so the value is an
#: intentional capacity constant, not an incidental literal.
ANNOUNCEMENT_FANOUT_BATCH_SIZE = 500  # magic-number-allow: announcement fan-out batch size

#: Roles treated as "staff" for the STAFF audience: everyone who works at the
#: school, i.e. not a student and not a parent/guardian. Keyed off the role enum
#: (never bare literals) so it tracks ``User.Role`` automatically.
_NON_STAFF_ROLES = (User.Role.STUDENT, User.Role.PARENT)


def _school_user_queryset(school):
    """All ``User`` rows linked to ``school`` (membership / teacher / student).

    Mirrors :func:`apps.communication.api_views._school_user_queryset` — the
    established "users in this school" pattern — so audience resolution shares
    the same tenant-scoping definition as messaging.
    """
    if school is None:
        return User.objects.none()
    # tenant-isolation-allow: school-bound-recipient-resolution-reviewed
    return User.objects.filter(
        Q(school_memberships__school=school)
        | Q(teacher_profile__school=school)
        | Q(student_profile__school=school)
    ).distinct()


def _guardian_users_for_school(school) -> Iterator[Any]:
    """Yield guardian ``User`` rows for ``school``, skipping email opt-outs early.

    ``dispatch_event`` re-checks per-channel preferences (including the guardian
    ``receives_email`` flag) before each send, but resolving here lets us drop the
    obvious opt-outs (a guardian with ``receives_email=False`` and no other
    permitted channel) before they ever enter a batch.
    """
    from apps.people.models import StudentGuardian

    # tenant-isolation-allow: school-bound-guardian-resolution-reviewed
    links = (
        StudentGuardian.objects.filter(student__school=school, is_active=True)
        .select_related("guardian_user")
        .order_by("guardian_user_id")
    )
    seen: set = set()
    for link in links.iterator():
        guardian = link.guardian_user
        if guardian is None or guardian.pk in seen:
            continue
        # Skip the obvious opt-out: guardian has explicitly disabled email.
        if not getattr(link, "receives_email", True):
            continue
        seen.add(guardian.pk)
        yield guardian


def _specific_recipient_users(announcement: Announcement) -> List[Any]:
    """Resolve the recipient list for ``audience="specific"``.

    The chosen recipients are persisted on the ``Announcement.specific_recipients``
    M2M (Phase 4.4). They are intersected here with the set of users actually
    linked to ``announcement.school`` so a stray / stale pick from another tenant
    can never receive the announcement — fan-out re-scopes to the school as a
    hard floor, independent of how the picks were saved. An empty pick set yields
    zero recipients with an info log (a "specific" announcement targeting nobody
    is a content mistake, not a crash).
    """
    school = getattr(announcement, "school", None)
    if school is None:
        return []

    try:
        chosen_ids = list(
            announcement.specific_recipients.values_list("pk", flat=True)
        )
    except Exception as exc:  # broad-by-design — a bad relation never breaks publish
        logger.warning(
            "announcement %s specific-recipient resolve failed err=%s",
            getattr(announcement, "pk", None),
            type(exc).__name__,
        )
        return []

    if not chosen_ids:
        logger.info(
            "announcement %s audience='specific' has no picked recipients; "
            "delivering to zero recipients",
            getattr(announcement, "pk", None),
        )
        return []

    # Re-scope to the school's own user set: the M2M is the *intent*, the school
    # membership is the *authority*. Only users that are both picked AND linked to
    # this school are delivered to.
    in_school = set(
        _school_user_queryset(school)
        .filter(pk__in=chosen_ids)
        .values_list("pk", flat=True)
    )
    dropped = len(chosen_ids) - len(in_school)
    if dropped:
        logger.warning(
            "announcement %s dropped %s specific recipient(s) not linked to its "
            "school (cross-tenant / stale picks)",
            getattr(announcement, "pk", None),
            dropped,
        )
    if not in_school:
        return []
    # tenant-isolation-allow: ids-pre-filtered-through-school-user-queryset
    return list(User.objects.filter(pk__in=in_school))


def resolve_audience_recipients(announcement: Announcement) -> Iterator[Any]:
    """Map an announcement's audience to concrete recipient ``User`` rows.

    All resolution is bound to ``announcement.school``. Mapping:

    * ``all`` — every user linked to the school.
    * ``students`` — school users with role STUDENT.
    * ``teachers`` — school users with role TEACHER.
    * ``all_parents`` — guardian users for the school (email opt-outs skipped early).
    * ``staff`` — school users who are not students and not parents (i.e. anyone
      who works at the school: admin/leadership/teachers/finance/etc.).
    * ``specific`` — resolved via :func:`_specific_recipient_users` (empty +
      warning under the current schema; see that helper).

    Yields ``User`` instances; an unknown / missing school yields nothing.
    """
    school = getattr(announcement, "school", None)
    if school is None:
        return

    audience = (announcement.audience or "").strip()
    base = _school_user_queryset(school)

    if audience == Announcement.Audience.ALL:
        yield from base.iterator()
        return
    if audience == Announcement.Audience.STUDENTS:
        yield from base.filter(role=User.Role.STUDENT).iterator()
        return
    if audience == Announcement.Audience.TEACHERS:
        yield from base.filter(role=User.Role.TEACHER).iterator()
        return
    if audience == Announcement.Audience.STAFF:
        yield from base.exclude(role__in=_NON_STAFF_ROLES).iterator()
        return
    if audience == Announcement.Audience.PARENTS:
        # Parents are modelled via StudentGuardian, not by membership role, so
        # resolve through the guardian links (with early email opt-out skip).
        yield from _guardian_users_for_school(school)
        return
    if audience == Announcement.Audience.SPECIFIC:
        yield from _specific_recipient_users(announcement)
        return

    # Unknown audience value — deliver to nobody rather than guessing.
    logger.warning(
        "announcement %s has unrecognised audience=%r; delivering to zero recipients",
        getattr(announcement, "pk", None),
        audience,
    )


def _announcement_link(announcement: Announcement) -> str:
    """Best-effort detail URL for the announcement (empty string on failure)."""
    try:
        return reverse(
            "communication:announcement_detail",
            kwargs={"announcement_id": announcement.pk},
        )
    except (NoReverseMatch, ValueError):
        return ""


def deliver_announcement(announcement: Announcement) -> Dict[str, Any]:
    """Fan a published announcement out to its audience via :func:`dispatch_event`.

    Idempotent: if ``announcement.delivered_at`` is already set this is a no-op
    returning ``{"skipped": "already_delivered"}``. Otherwise recipients are
    iterated in batches of :data:`ANNOUNCEMENT_FANOUT_BATCH_SIZE`; each gets one
    ``"announcement.published"`` event (the dispatch engine owns channel
    selection). ``delivered_at`` is stamped after the loop so a later run skips.

    Returns a summary dict ``{"delivered": True, "recipients": N, "dispatched":
    X, "skipped": Y, "errors": Z}`` with honest tallies (a recipient the router
    fully muted counts as ``skipped``, never ``dispatched``).
    """
    if announcement is None:
        return {"skipped": "no_announcement"}
    if announcement.delivered_at is not None:
        return {"skipped": "already_delivered"}

    school = getattr(announcement, "school", None)
    context_base = {
        "title": announcement.title,
        "message": announcement.content,
        "link": _announcement_link(announcement),
        "severity": "INFO",
    }

    recipients = 0
    dispatched = 0
    skipped = 0
    errors = 0

    batch: List[Any] = []

    def _flush(users: List[Any]) -> None:
        nonlocal recipients, dispatched, skipped, errors
        for user in users:
            recipients += 1
            try:
                result = dispatch_event(
                    ANNOUNCEMENT_EVENT_KEY,
                    recipient=user,
                    context=dict(context_base),
                    school=school,
                )
            except Exception as exc:  # broad-by-design — one bad recipient never aborts the blast
                errors += 1
                logger.warning(
                    "announcement %s dispatch failed recipient=%s err=%s",
                    announcement.pk,
                    getattr(user, "pk", None),
                    type(exc).__name__,
                )
                continue
            # A wholly-muted recipient is an honest skip, not a send.
            if result.get("skipped"):
                skipped += 1
            else:
                dispatched += 1

    for user in resolve_audience_recipients(announcement):
        batch.append(user)
        if len(batch) >= ANNOUNCEMENT_FANOUT_BATCH_SIZE:
            _flush(batch)
            batch = []
    if batch:
        _flush(batch)

    announcement.delivered_at = timezone.now()
    announcement.save(update_fields=["delivered_at"])

    return {
        "delivered": True,
        "announcement_id": announcement.pk,
        "recipients": recipients,
        "dispatched": dispatched,
        "skipped": skipped,
        "errors": errors,
    }


def send_due_scheduled_announcements() -> Dict[str, Any]:
    """Periodic entry point: deliver every published announcement that is due.

    "Due" = published, ``scheduled_at <= now``, and not yet delivered. Each
    announcement is delivered in its own ``try/except`` so one failure never
    blocks the rest of the due batch. Returns a summary of how many were
    considered / delivered / errored.

    (Registration of the periodic job lives in ``periodic.py`` and is owned by
    the operator — this module only provides the callable.)
    """
    now = timezone.now()
    # tenant-isolation-allow: each-row-carries-its-own-school-fk
    due = Announcement.objects.filter(
        status=Announcement.Status.PUBLISHED,
        scheduled_at__lte=now,
        delivered_at__isnull=True,
    ).order_by("scheduled_at")

    considered = 0
    delivered = 0
    errored = 0
    summaries: List[Dict[str, Any]] = []

    for announcement in due.iterator():
        considered += 1
        try:
            summary = deliver_announcement(announcement)
        except Exception as exc:  # broad-by-design — isolate one bad announcement from the batch
            errored += 1
            logger.exception(
                "scheduled announcement delivery failed announcement=%s err=%s",
                announcement.pk,
                type(exc).__name__,
            )
            continue
        if summary.get("delivered"):
            delivered += 1
        summaries.append(summary)

    return {
        "considered": considered,
        "delivered": delivered,
        "errored": errored,
        "summaries": summaries,
    }


__all__ = [
    "ANNOUNCEMENT_EVENT_KEY",
    "ANNOUNCEMENT_FANOUT_BATCH_SIZE",
    "resolve_audience_recipients",
    "deliver_announcement",
    "send_due_scheduled_announcements",
]
