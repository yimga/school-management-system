"""Family surface — a student's own team + a parent's children's teams/fixtures.

No ``athletics.*`` permission is required (families never hold those codes); access is
scoped object-by-object to the requester's OWN self (student) or children (parent) via
the canonical ``effective_access.student_data_access`` check, so a parent only ever
sees their own child's roster, fixtures, and pending consent.
"""

from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods

from apps.athletics.constants import FAMILY_FIXTURE_LIST_LIMIT
from apps.athletics.models import (
    Club,
    ClubMembership,
    Fixture,
    ParticipationConsent,
    ParticipationConsentDecision,
    TeamMembership,
)
from apps.athletics.services.clubs import ClubError, enroll_student
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
@require_http_methods(["GET", "POST"])
def family_my_team(request):
    """Student 'my team' + parent 'child's team/clubs/fixtures + pending consent'."""
    school = request.school
    students = _scoped_students(request)
    student_ids = {s.id for s in students}

    if request.method == "POST":
        intent = (request.POST.get("intent") or "").strip()
        if intent == "enroll_club":
            club_id = (request.POST.get("club_id") or "").strip()
            student_id_raw = (request.POST.get("student_id") or "").strip()
            if not club_id.isdigit() or not student_id_raw.isdigit():
                messages.error(request, "Select a valid club and student.")
            else:
                sid = int(student_id_raw)
                if sid not in student_ids:
                    messages.error(request, "You can only enroll your own children.")
                else:
                    club = Club.objects.filter(
                        pk=int(club_id),
                        school=school,
                        status=Club.Status.ACTIVE,
                    ).first()
                    student = next((s for s in students if s.id == sid), None)
                    if club is None or student is None:
                        messages.error(request, "Club not available for enrollment.")
                    else:
                        try:
                            membership = enroll_student(club=club, student=student)
                            if membership.status == ClubMembership.Status.WAITLIST:
                                messages.success(
                                    request,
                                    f"Added to the waitlist for “{club.name}”.",
                                )
                            else:
                                messages.success(
                                    request,
                                    f"Enrolled in “{club.name}”.",
                                )
                        except ClubError as exc:
                            messages.error(request, str(exc))
            return redirect("athletics:family_my_team")

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

    # tenant-isolation-allow: school-scoped-club-memberships-for-guardian-students
    club_memberships = list(
        ClubMembership.objects.filter(
            school=school,
            student_id__in=student_ids,
            status__in=ClubMembership.ROSTER_ACTIVE_STATUSES,
        ).select_related("club", "student")
        .order_by("student__last_name", "club__name")
    )
    enrolled_club_ids = {m.club_id for m in club_memberships}
    # tenant-isolation-allow: school-scoped-open-clubs-for-family-enroll-cta
    open_clubs = list(
        Club.objects.filter(school=school, status=Club.Status.ACTIVE)
        .exclude(pk__in=enrolled_club_ids)
        .order_by("name")
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
            "club_memberships": club_memberships,
            "open_clubs": open_clubs,
        },
    )
