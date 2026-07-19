"""Clubs admin console — list/create clubs and manage memberships.

Read gates on ``athletics.view``/``athletics.manage``; create/enroll/withdraw
require ``athletics.manage``. Every queryset is ``request.school``-scoped.
"""

from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.accounts.decorators import require_permission
from apps.athletics.forms import ClubForm, EnrollClubMemberForm
from apps.athletics.models import Club, ClubMembership
from apps.athletics.services.clubs import ClubError, create_club, enroll_student, withdraw_member
from apps.schools.mixins import require_school


def _require_manage(request) -> None:
    from apps.accounts import effective_access

    if not effective_access.permission_access(
        request.user, getattr(request, "school", None), ("athletics.manage",)
    ):
        raise PermissionDenied


@login_required
@require_school
@require_permission("athletics.view", "athletics.manage")
def admin_clubs(request):
    """List clubs and create new ones (create requires athletics.manage)."""
    school = request.school

    if request.method == "POST":
        _require_manage(request)
        form = ClubForm(request.POST, school=school)
        form.instance.school = school
        if form.is_valid():
            try:
                club = create_club(
                    school=school,
                    name=form.cleaned_data["name"],
                    category=form.cleaned_data.get("category") or "",
                    description=form.cleaned_data.get("description") or "",
                    meeting_day=form.cleaned_data.get("meeting_day") or "",
                    meeting_location=form.cleaned_data.get("meeting_location") or "",
                    capacity=form.cleaned_data.get("capacity"),
                    academic_year=form.cleaned_data.get("academic_year"),
                    status=form.cleaned_data.get("status") or Club.Status.FORMING,
                )
            except ClubError as exc:
                messages.error(request, str(exc))
            else:
                messages.success(request, f"Club '{club.name}' created.")
                return redirect("athletics:admin_club_detail", club_id=club.id)
            messages.error(request, "Please correct the errors below.")
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        form = ClubForm(school=school)

    clubs = (
        Club.objects.filter(school=school)
        .exclude(status=Club.Status.ARCHIVED)
        .select_related("academic_year")
        .order_by("name")
    )
    return render(
        request,
        "athletics/admin/clubs.html",
        {"school": school, "clubs": clubs, "form": form},
    )


@login_required
@require_school
@require_permission("athletics.view", "athletics.manage")
def admin_club_detail(request, club_id):
    """Club roster + enroll form."""
    school = request.school
    club = get_object_or_404(
        Club.objects.filter(school=school).select_related("academic_year"),
        pk=club_id,
    )
    memberships = (
        ClubMembership.objects.filter(school=school, club=club)
        .select_related("student")
        .order_by("status", "student__last_name", "student__first_name")
    )
    enroll_form = EnrollClubMemberForm(school=school)
    can_manage = False
    try:
        from apps.accounts import effective_access

        can_manage = effective_access.permission_access(
            request.user, school, ("athletics.manage",)
        )
    except Exception:  # noqa: BLE001
        can_manage = False
    return render(
        request,
        "athletics/admin/club_detail.html",
        {
            "school": school,
            "club": club,
            "memberships": memberships,
            "enroll_form": enroll_form,
            "can_manage": can_manage,
        },
    )


@login_required
@require_school
@require_permission("athletics.manage")
@require_POST
def admin_club_enroll(request, club_id):
    """POST enroll a student onto a club (waitlists at capacity)."""
    school = request.school
    club = get_object_or_404(Club.objects.filter(school=school), pk=club_id)
    form = EnrollClubMemberForm(request.POST, school=school)
    if not form.is_valid():
        messages.error(request, "Please select a student to enroll.")
        return redirect("athletics:admin_club_detail", club_id=club.id)
    try:
        membership = enroll_student(
            club=club,
            student=form.cleaned_data["student"],
            role_title=form.cleaned_data.get("role_title") or "",
        )
    except ClubError as exc:
        messages.error(request, str(exc))
    else:
        if membership.status == ClubMembership.Status.WAITLIST:
            messages.info(
                request,
                f"{membership.student} added to the waitlist (club at capacity).",
            )
        else:
            messages.success(request, f"{membership.student} enrolled in {club.name}.")
    return redirect("athletics:admin_club_detail", club_id=club.id)


@login_required
@require_school
@require_permission("athletics.manage")
@require_POST
def admin_club_withdraw(request, membership_id):
    """POST withdraw a club membership."""
    school = request.school
    membership = get_object_or_404(
        ClubMembership.objects.filter(school=school).select_related("club"),
        pk=membership_id,
    )
    club_id = membership.club_id
    try:
        withdraw_member(membership=membership)
    except ClubError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, "Member withdrawn from the club.")
    return redirect("athletics:admin_club_detail", club_id=club_id)
