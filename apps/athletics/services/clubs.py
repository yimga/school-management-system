"""Club lifecycle mutations — create, advisor assign, enroll / withdraw.

All writes are school-scoped. Capacity is a hard cap: enrollments beyond
``club.capacity`` land on the waitlist rather than raising, so operators can
still capture demand.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from django.db import transaction
from django.utils.text import slugify

from apps.athletics.constants import DEFAULT_CLUB_CAPACITY
from apps.athletics.models import (
    Club,
    ClubAdvisorAssignment,
    ClubCategory,
    ClubMembership,
)


class ClubError(Exception):
    """User-facing club mutation failure."""


class ClubCapacityError(ClubError):
    """Raised when an operator forces ACTIVE past capacity (waitlist preferred)."""


def _active_count(club: Club) -> int:
    return ClubMembership.objects.filter(
        school_id=club.school_id,
        club=club,
        status=ClubMembership.Status.ACTIVE,
    ).count()


@transaction.atomic
def create_club(
    *,
    school: Any,
    name: str,
    category: str = ClubCategory.OTHER,
    description: str = "",
    meeting_day: str = "",
    meeting_location: str = "",
    capacity: int | None = None,
    academic_year: Any = None,
    status: str = Club.Status.FORMING,
    slug: str = "",
) -> Club:
    """Create a school-scoped club. Slug auto-derived from name when omitted."""
    name = (name or "").strip()
    if not name:
        raise ClubError("Club name is required.")
    if school is None:
        raise ClubError("School is required.")

    club = Club(
        school=school,
        academic_year=academic_year,
        name=name,
        slug=(slug or slugify(name)[:120] or "club"),
        category=category or ClubCategory.OTHER,
        description=(description or "").strip(),
        meeting_day=(meeting_day or "").strip(),
        meeting_location=(meeting_location or "").strip(),
        capacity=int(capacity) if capacity is not None else DEFAULT_CLUB_CAPACITY,
        status=status or Club.Status.FORMING,
    )
    club.save()
    return club


@transaction.atomic
def assign_advisor(
    *,
    club: Club,
    advisor: Any,
    role: str = ClubAdvisorAssignment.Role.LEAD,
) -> ClubAdvisorAssignment:
    """Activate (or create) an advisor assignment for ``advisor`` on ``club``."""
    if club is None or advisor is None:
        raise ClubError("Club and advisor are required.")
    existing = ClubAdvisorAssignment.objects.filter(
        school_id=club.school_id,
        club=club,
        advisor=advisor,
        is_active=True,
    ).first()
    if existing is not None:
        if existing.role != role:
            existing.role = role
            existing.save(update_fields=["role"])
        return existing
    return ClubAdvisorAssignment.objects.create(
        school_id=club.school_id,
        club=club,
        advisor=advisor,
        role=role or ClubAdvisorAssignment.Role.LEAD,
        is_active=True,
    )


@transaction.atomic
def enroll_student(
    *,
    club: Club,
    student: Any,
    role_title: str = "",
    joined_on: date | None = None,
    force_active: bool = False,
) -> ClubMembership:
    """Enroll a student; waitlist when active roster is at capacity."""
    if club is None or student is None:
        raise ClubError("Club and student are required.")
    if getattr(student, "school_id", None) != club.school_id:
        raise ClubError("Student must belong to the same school as the club.")

    existing = (
        ClubMembership.objects.filter(
            school_id=club.school_id,
            club=club,
            student=student,
            status__in=ClubMembership.ROSTER_ACTIVE_STATUSES,
        )
        .order_by("id")
        .first()
    )
    if existing is not None:
        return existing

    at_capacity = _active_count(club) >= int(club.capacity or DEFAULT_CLUB_CAPACITY)
    if at_capacity and force_active:
        raise ClubCapacityError("Club is at capacity; cannot force an active seat.")
    status = (
        ClubMembership.Status.WAITLIST
        if at_capacity
        else ClubMembership.Status.ACTIVE
    )
    return ClubMembership.objects.create(
        school_id=club.school_id,
        club=club,
        student=student,
        role_title=(role_title or "").strip(),
        status=status,
        joined_at=joined_on or date.today(),
    )


@transaction.atomic
def withdraw_member(*, membership: ClubMembership) -> ClubMembership:
    """Mark a membership LEFT (idempotent if already left)."""
    if membership is None:
        raise ClubError("Membership is required.")
    if membership.status == ClubMembership.Status.LEFT:
        return membership
    membership.status = ClubMembership.Status.LEFT
    membership.left_at = date.today()
    membership.save(update_fields=["status", "left_at", "updated_at"])
    return membership


__all__ = [
    "ClubCapacityError",
    "ClubError",
    "assign_advisor",
    "create_club",
    "enroll_student",
    "withdraw_member",
]
