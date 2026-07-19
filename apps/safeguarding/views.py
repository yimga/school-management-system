"""Tenant safeguarding UI — raise concern + DSL inbox/triage (metric #11)."""

from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.translation import gettext as _
from django.views.decorators.http import require_http_methods

from apps.safeguarding.concern_kernel import (
    ACKNOWLEDGED,
    ACTION_TAKEN,
    CLOSED,
    REFERRED_EXTERNAL,
    DSLRoleRequired,
    InvalidConcernTransition,
)
from apps.safeguarding.services import (
    acknowledge_and_transition,
    enabled_categories_for_school,
    find_concern,
    inbox_rows,
    open_concern_rows,
    submit_concern_for_school,
    user_is_dsl,
)
from apps.schools.mixins import require_school
from services.post_delete_navigation import redirect_after_save


def _redirect_inbox(request):
    target = reverse("accounts:safeguarding_inbox")
    return redirect_after_save(request, target, list_url=target)


@login_required
@require_school
@require_http_methods(["GET", "POST"])
def safeguarding_raise(request):
    """Teacher/staff raise a safeguarding concern."""
    school = request.school
    categories = enabled_categories_for_school(school)
    if request.method == "POST":
        category_key = (request.POST.get("category_key") or "").strip()
        narrative = (request.POST.get("narrative") or "").strip()
        student_raw = (request.POST.get("student_id") or "").strip()
        student_id = int(student_raw) if student_raw.isdigit() else None
        try:
            entry = submit_concern_for_school(
                school=school,
                reporter_user_id=int(request.user.pk),
                category_key=category_key,
                narrative=narrative,
                student_id=student_id,
            )
        except ValueError as exc:
            messages.error(request, str(exc))
        else:
            messages.success(
                request,
                _("Safeguarding concern submitted (%(id)s).")
                % {"id": entry.concern_id[:8]},
            )
            if user_is_dsl(request.user, school):
                return redirect(
                    "accounts:safeguarding_concern_detail",
                    concern_id=entry.concern_id,
                )
            return redirect("accounts:safeguarding_raise")

    return render(
        request,
        "safeguarding/raise_concern.html",
        {
            "school": school,
            "categories": categories,
            "inbox_url": reverse("accounts:safeguarding_inbox"),
            "is_dsl": user_is_dsl(request.user, school),
        },
    )


@login_required
@require_school
@require_http_methods(["GET"])
def safeguarding_inbox(request):
    """DSL inbox of unacknowledged concerns."""
    school = request.school
    if not user_is_dsl(request.user, school):
        messages.error(request, _("Only the Designated Safeguarding Lead can open this inbox."))
        return redirect("accounts:safeguarding_raise")

    return render(
        request,
        "safeguarding/dsl_inbox.html",
        {
            "school": school,
            "inbox": inbox_rows(school),
            "open_concerns": open_concern_rows(school),
            "raise_url": reverse("accounts:safeguarding_raise"),
        },
    )


@login_required
@require_school
@require_http_methods(["GET", "POST"])
def safeguarding_concern_detail(request, concern_id: str):
    school = request.school
    concern = find_concern(school, concern_id)
    if concern is None:
        raise Http404("concern_not_found")

    is_dsl = user_is_dsl(request.user, school)
    is_reporter = int(request.user.pk) == int(concern.reporter_user_id)
    if not (is_dsl or is_reporter or request.user.is_superuser):
        messages.error(request, _("You do not have access to this concern."))
        return redirect("accounts:safeguarding_raise")

    if request.method == "POST":
        if not is_dsl:
            messages.error(request, _("Only a DSL can advance this concern."))
            return redirect(
                "accounts:safeguarding_concern_detail",
                concern_id=concern_id,
            )
        target = (request.POST.get("target_stage") or "").strip()
        note = (request.POST.get("note") or "").strip()
        referral = (request.POST.get("referral_reference") or "").strip()
        entry_id = (request.POST.get("inbox_entry_id") or "").strip()
        try:
            acknowledge_and_transition(
                school=school,
                concern_id=concern_id,
                actor_user_id=int(request.user.pk),
                target_stage=target,
                note=note,
                referral_reference=referral,
                inbox_entry_id=entry_id,
            )
        except (ValueError, InvalidConcernTransition, DSLRoleRequired) as exc:
            messages.error(request, str(exc))
        else:
            messages.success(request, _("Concern updated to %(stage)s.") % {"stage": target})
            return _redirect_inbox(request)

    return render(
        request,
        "safeguarding/concern_detail.html",
        {
            "school": school,
            "concern": concern,
            "is_dsl": is_dsl,
            "inbox_url": reverse("accounts:safeguarding_inbox"),
            "transition_choices": [
                ACKNOWLEDGED,
                ACTION_TAKEN,
                REFERRED_EXTERNAL,
                CLOSED,
            ],
        },
    )
