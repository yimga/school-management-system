"""Coach console — my teams, roster, eligibility board, fixtures, consent.

Read surfaces gate on ``athletics.view``/``athletics.manage``; write surfaces gate on
``athletics.manage`` AND additionally on the object-level ``assert_team_manage`` check
so a coach can only mutate the teams they are assigned to. Every queryset is
``request.school``-scoped. Service mutations (schedule fixture / record result / mint
consent) run through ``apps.athletics.services.*`` and their user-facing exceptions
(``BookingConflictError`` / ``ParticipationConsentError``) render as messages.
"""

from __future__ import annotations

import logging

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.views.decorators.http import require_POST

from apps.accounts.decorators import require_permission
from apps.athletics.constants import CONSENT_TEXT_VERSION
from apps.athletics.forms import (
    AddMemberForm,
    RecordResultForm,
    RequestConsentForm,
    ScheduleFixtureForm,
)
from apps.athletics.models import (
    EligibilityRecord,
    Fixture,
    ParticipationConsentError,
    Team,
    TeamMembership,
)
from apps.athletics.views._common import (
    assert_team_manage,
    coach_team_qs,
    eligibility_board,
)
from apps.schools.mixins import require_school

logger = logging.getLogger(__name__)


@login_required
@require_school
@require_permission("athletics.view", "athletics.manage")
def coach_dashboard(request):
    """My-teams list with a per-team eligibility board."""
    school = request.school
    teams = coach_team_qs(request).select_related("sport", "season")
    cards = [{"team": team, "board": eligibility_board(team)} for team in teams]
    return render(
        request,
        "athletics/coach/dashboard.html",
        {"school": school, "cards": cards},
    )


@login_required
@require_school
@require_permission("athletics.view", "athletics.manage")
def coach_team_detail(request, team_id):
    """Roster detail for a single team (add-member + request-consent forms)."""
    school = request.school
    team = get_object_or_404(
        coach_team_qs(request).select_related("sport", "season"), pk=team_id
    )
    memberships = (
        TeamMembership.objects.filter(school=school, team=team)
        .select_related("student")
        .order_by("status", "jersey_number")
    )
    can_manage = _can_manage(request, team.id)
    return render(
        request,
        "athletics/coach/team_detail.html",
        {
            "school": school,
            "team": team,
            "memberships": memberships,
            "can_manage": can_manage,
            "add_form": AddMemberForm(school=school),
            "consent_form": RequestConsentForm(),
            "member_statuses": TeamMembership.Status,
        },
    )


@login_required
@require_school
@require_permission("athletics.view", "athletics.manage")
def coach_eligibility(request, team_id):
    """Per-athlete eligibility board; POST recomputes via the resolver."""
    school = request.school
    team = get_object_or_404(coach_team_qs(request), pk=team_id)
    memberships = list(
        TeamMembership.objects.filter(
            school=school,
            team=team,
            status__in=TeamMembership.ROSTER_ACTIVE_STATUSES,
        ).select_related("student")
    )

    if request.method == "POST":
        assert_team_manage(request, team.id)  # recompute is a write
        from apps.athletics.services.eligibility import resolve_eligibility

        recomputed = 0
        for membership in memberships:
            try:
                resolve_eligibility(
                    membership=membership,
                    request=request,
                    actor=request.user,
                    persist=True,
                )
                recomputed += 1
            except Exception:  # noqa: BLE001 — one bad row must not abort the sweep
                logger.warning(
                    "athletics_eligibility_recompute_failed membership=%s",
                    membership.id,
                )
        messages.success(request, f"Recomputed eligibility for {recomputed} athletes.")
        return redirect("athletics:coach_eligibility", team_id=team.id)

    records = EligibilityRecord.objects.filter(
        school=school, membership__team=team
    ).order_by("membership", "-checked_at")
    latest: dict = {}
    for rec in records:
        latest.setdefault(rec.membership_id, rec)
    rows = [
        {"membership": membership, "record": latest.get(membership.id)}
        for membership in memberships
    ]
    return render(
        request,
        "athletics/coach/eligibility.html",
        {
            "school": school,
            "team": team,
            "rows": rows,
            "can_manage": _can_manage(request, team.id),
        },
    )


@login_required
@require_school
@require_permission("athletics.view", "athletics.manage")
def coach_fixtures(request, team_id):
    """Fixtures list for a team + schedule-fixture and record-result forms."""
    school = request.school
    team = get_object_or_404(coach_team_qs(request).select_related("season"), pk=team_id)
    fixtures = (
        Fixture.objects.filter(school=school, team=team)
        .select_related("venue", "result")
        .order_by("scheduled_start")
    )
    return render(
        request,
        "athletics/coach/fixtures.html",
        {
            "school": school,
            "team": team,
            "fixtures": fixtures,
            "can_manage": _can_manage(request, team.id),
            "schedule_form": ScheduleFixtureForm(school=school),
            "result_form": RecordResultForm(),
        },
    )


@login_required
@require_school
@require_permission("athletics.manage")
@require_POST
def coach_schedule_fixture(request, team_id):
    """Schedule a fixture through the scheduling service (books the venue)."""
    school = request.school
    team = get_object_or_404(Team.objects.filter(school=school), pk=team_id)
    assert_team_manage(request, team.id)
    form = ScheduleFixtureForm(request.POST, school=school)
    if not form.is_valid():
        messages.error(request, "Please correct the errors in the schedule form.")
        return redirect("athletics:coach_fixtures", team_id=team.id)

    from apps.athletics.services.booking import BookingConflictError
    from apps.athletics.services.scheduling import schedule_fixture

    data = form.cleaned_data
    try:
        schedule_fixture(
            team=team,
            opponent_name=data["opponent_name"],
            fixture_type=data["fixture_type"],
            venue=data.get("venue"),
            start=data["scheduled_start"],
            end=data["scheduled_end"],
            actor=request.user,
            book_venue=bool(data.get("book_venue")),
        )
        messages.success(request, "Fixture scheduled.")
    except BookingConflictError:
        messages.error(
            request,
            "That venue is already booked for an overlapping time — pick another slot or venue.",
        )
    return redirect("athletics:coach_fixtures", team_id=team.id)


@login_required
@require_school
@require_permission("athletics.manage")
@require_POST
def coach_record_result(request, fixture_id):
    """Record a fixture's final score through the scheduling service."""
    school = request.school
    fixture = get_object_or_404(
        Fixture.objects.filter(school=school).select_related("team"), pk=fixture_id
    )
    assert_team_manage(request, fixture.team_id)
    form = RecordResultForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Please enter valid scores.")
        return redirect("athletics:coach_fixtures", team_id=fixture.team_id)

    from apps.athletics.services.scheduling import record_result

    data = form.cleaned_data
    result = record_result(
        fixture=fixture,
        home_score=data["home_score"],
        away_score=data["away_score"],
        actor=request.user,
    )
    notes = data.get("notes")
    if notes and result is not None:
        result.notes = notes
        result.save(update_fields=["notes"])
    messages.success(request, "Result recorded.")
    return redirect("athletics:coach_fixtures", team_id=fixture.team_id)


@login_required
@require_school
@require_permission("athletics.manage")
@require_POST
def coach_cancel_fixture(request, fixture_id):
    """Cancel a fixture and free every venue booking it holds."""
    school = request.school
    fixture = get_object_or_404(
        Fixture.objects.filter(school=school).select_related("team"), pk=fixture_id
    )
    assert_team_manage(request, fixture.team_id)

    from apps.athletics.services.scheduling import cancel_fixture

    try:
        cancel_fixture(fixture=fixture, actor=request.user)
        messages.success(request, "Fixture cancelled and its venue released.")
    except ValueError as exc:
        messages.error(request, str(exc) or "That fixture can't be cancelled.")
    return redirect("athletics:coach_fixtures", team_id=fixture.team_id)


@login_required
@require_school
@require_permission("athletics.manage")
@require_POST
def coach_request_consent(request, membership_id):
    """Mint a guardian participation-consent token for a pending membership."""
    school = request.school
    membership = get_object_or_404(
        TeamMembership.objects.filter(school=school).select_related("team", "student"),
        pk=membership_id,
    )
    assert_team_manage(request, membership.team_id)
    form = RequestConsentForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Enter a valid guardian name and email.")
        return redirect("athletics:coach_team_detail", team_id=membership.team_id)

    consent_text = render_to_string(
        "athletics/consent/_consent_text_v1.html",
        {
            "membership": membership,
            "team": membership.team,
            "student": membership.student,
            "school": school,
        },
        request=request,
    )
    from apps.athletics.services.consent import request_participation_consent

    data = form.cleaned_data
    try:
        request_participation_consent(
            membership=membership,
            guardian_name=data["guardian_name"],
            guardian_email=data["guardian_email"],
            consent_text=consent_text,
            version=CONSENT_TEXT_VERSION,
        )
        messages.success(
            request,
            f"Participation-consent request sent to {data['guardian_email']}.",
        )
    except ParticipationConsentError as exc:
        messages.error(request, str(exc) or "Could not send the consent request.")
    return redirect("athletics:coach_team_detail", team_id=membership.team_id)


@login_required
@require_school
@require_permission("athletics.manage")
@require_POST
def coach_add_member(request, team_id):
    """Add a student to the roster as a pending (consent-gated) membership."""
    school = request.school
    team = get_object_or_404(Team.objects.filter(school=school), pk=team_id)
    assert_team_manage(request, team.id)
    form = AddMemberForm(request.POST, school=school)
    if not form.is_valid():
        messages.error(request, "Select a student to add to the roster.")
        return redirect("athletics:coach_team_detail", team_id=team.id)

    student = form.cleaned_data["student"]
    already = TeamMembership.objects.filter(
        school=school,
        team=team,
        student=student,
        status__in=TeamMembership.ROSTER_ACTIVE_STATUSES,
    ).exists()
    if already:
        messages.error(request, "That student is already on this roster.")
        return redirect("athletics:coach_team_detail", team_id=team.id)

    TeamMembership.objects.create(
        school=school,
        team=team,
        student=student,
        jersey_number=form.cleaned_data.get("jersey_number"),
        position=form.cleaned_data.get("position") or "",
        status=TeamMembership.Status.PENDING,
    )
    messages.success(
        request, "Student added — request guardian consent to activate them."
    )
    return redirect("athletics:coach_team_detail", team_id=team.id)


def _can_manage(request, team_id) -> bool:
    from apps.athletics.views._common import team_manage_allowed

    return team_manage_allowed(request.user, request.school, team_id)
