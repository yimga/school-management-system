"""Family surface — a student's own team + a parent's children's teams/fixtures.

No ``athletics.*`` permission is required (families never hold those codes); access is
scoped object-by-object to the requester's OWN self (student) or children (parent) via
the canonical ``effective_access.student_data_access`` check, so a parent only ever
sees their own child's roster, fixtures, and pending consent.
"""

from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from apps.athletics.constants import FAMILY_FIXTURE_LIST_LIMIT
from apps.athletics.models import (
    Fixture,
    ParticipationConsent,
    ParticipationConsentDecision,
    TeamMembership,
)
from apps.schools.mixins import require_school


def _scoped_students(request):
    """StudentProfiles the caller may view in this school: own self + own children."""
    from apps.accounts import effective_access
    from apps.people.models import StudentProfile
    from apps.portal.services import guardian_students

    school = request.school
    user = request.user
    students: dict = {}

    for profile in StudentProfile.objects.filter(school=school, user=user):
        students[profile.id] = profile

    for child in guardian_students(user):
        if getattr(child, "school_id", None) != school.id:
            continue
        if child.id in students:
            continue
        if effective_access.student_data_access(user, child.id):
            students[child.id] = child

    return list(students.values())


@login_required
@require_school
def family_my_team(request):
    """Student 'my team' + parent 'child's team/fixtures + pending consent to sign'."""
    school = request.school
    students = _scoped_students(request)

    memberships = list(
        TeamMembership.objects.filter(
            school=school,
            student__in=students,
            status__in=TeamMembership.ROSTER_ACTIVE_STATUSES,
        ).select_related("team", "team__sport", "student")
    )
    team_ids = {membership.team_id for membership in memberships}

    fixtures = (
        Fixture.objects.filter(school=school, team_id__in=team_ids)
        .select_related("team", "venue", "result")
        .order_by("scheduled_start")[:FAMILY_FIXTURE_LIST_LIMIT]
    )

    pending_consents = (
        ParticipationConsent.objects.filter(
            school=school,
            membership__in=memberships,
            decision=ParticipationConsentDecision.PENDING,
        )
        .select_related("membership", "membership__team", "membership__student")
        .order_by("-token_issued_at")
    )

    return render(
        request,
        "athletics/family/my_team.html",
        {
            "school": school,
            "students": students,
            "memberships": memberships,
            "fixtures": fixtures,
            "pending_consents": pending_consents,
        },
    )
