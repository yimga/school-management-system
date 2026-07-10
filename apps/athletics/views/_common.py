"""Shared helpers for the athletics HTTP layer (coach / family / admin surfaces)."""

from __future__ import annotations

from django.core.exceptions import PermissionDenied

from apps.athletics.models import EligibilityRecord, Team, TeamMembership


def has_full_athletics_access(request) -> bool:
    """True when the caller is the athletics manager/admin tier (sees every team).

    A coach who only holds ``athletics.view`` is NOT full-access — they are scoped
    to the teams they are actively assigned to (``CoachAssignment``).
    """
    from apps.accounts import effective_access

    return effective_access.permission_access(
        request.user, getattr(request, "school", None), ("athletics.manage",)
    )


def coach_team_qs(request):
    """Teams the caller may see: all (manager tier) or only their assigned teams."""
    school = request.school
    base = Team.objects.filter(school=school).exclude(status=Team.Status.DISBANDED)
    if has_full_athletics_access(request):
        return base
    return base.filter(
        school=school,
        coach_assignments__coach=request.user,
        coach_assignments__is_active=True,
    ).distinct()


def team_manage_allowed(user, school, team_id) -> bool:
    """Object-level coach/admin gate for MUTATING a specific team.

    Delegates to the effective-access facade helper ``athletics_team_manage_access``
    (added by the RBAC builder). Falls back to the granular ``athletics.manage`` gate
    if the facade helper is not present yet, so the surface never hard-crashes during
    the parallel build window. Fails closed when no school is in context.
    """
    if school is None:
        return False
    from apps.accounts import effective_access

    checker = getattr(effective_access, "athletics_team_manage_access", None)
    if callable(checker):
        return bool(checker(user, school, team_id))
    return effective_access.permission_access(user, school, ("athletics.manage",))


def assert_team_manage(request, team_id) -> None:
    """Raise PermissionDenied (branded 403) unless the caller may mutate the team."""
    if not team_manage_allowed(request.user, getattr(request, "school", None), team_id):
        raise PermissionDenied


def eligibility_board(team) -> dict:
    """Tally a team's roster by its latest per-membership eligibility status."""
    memberships = list(
        TeamMembership.objects.filter(
            school_id=team.school_id,
            team=team,
            status__in=TeamMembership.ROSTER_ACTIVE_STATUSES,
        )
    )
    records = EligibilityRecord.objects.filter(
        school_id=team.school_id, membership__team=team
    ).order_by("membership", "-checked_at")
    latest: dict = {}
    for rec in records:
        latest.setdefault(rec.membership_id, rec)
    board = {
        "total": len(memberships),
        "eligible": 0,
        "ineligible": 0,
        "provisional": 0,
        "pending": 0,
    }
    for member in memberships:
        rec = latest.get(member.id)
        status = rec.status if rec is not None else EligibilityRecord.Status.PENDING
        board[status] = board.get(status, 0) + 1
    return board
