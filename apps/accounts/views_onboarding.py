"""
First-login checklist and Setup Studio entry.
Dashboard assembly and recommendation logic live in apps.dashboard.context and recommendation_service.
"""

import re

from django.contrib.auth.decorators import login_required
from django.contrib.auth.decorators import user_passes_test
from django.db import DatabaseError
from django.shortcuts import redirect
from django.urls import reverse
from django.views.decorators.http import require_POST
from django.http import JsonResponse

from .decorators import permission_required
from .views import _is_admin_user


@login_required
@permission_required("settings.manage")
@user_passes_test(_is_admin_user)
def dismiss_first_login_checklist(request):
    """W1-6: Dismiss the first-login checklist for this user (persisted in DashboardUserPreference)."""
    try:
        from apps.runtime_blueprints.models import DashboardUserPreference

        pref, _ = DashboardUserPreference.objects.get_or_create(
            user=request.user, defaults={"dashboard_layout": {}}
        )
        layout = dict(pref.dashboard_layout or {})
        layout["first_login_checklist_dismissed"] = True
        pref.dashboard_layout = layout
        pref.save(update_fields=["dashboard_layout"])
    except (AttributeError, TypeError, ValueError, DatabaseError):
        pass
    next_url = (
        request.POST.get("next")
        or request.GET.get("next")
        or reverse("accounts:backend_dashboard")
    )
    return redirect(next_url)


@login_required
@require_POST
def owner_confirm_role(request):
    """Record the first-login owner's decision (Owner Console — slice 1).

    ``decision`` (POST param) is ``confirm`` (stay owner) or ``defer`` (decide
    later); either way we stamp a per-school acknowledgement in
    ``DashboardUserPreference`` so the first-login card never shows again. This
    only *records* a decision — it grants no new authority and never touches
    ``is_staff``. Returns JSON for the card's fetch; falls back to a redirect for
    a plain form POST.
    """
    from apps.accounts.owner_first_login import (
        ACK_CONFIRMED,
        ACK_DEFERRED,
        _resolve_school,
        owner_ack_key,
    )

    decision = (request.POST.get("decision") or "confirm").strip().lower()
    ack = ACK_DEFERRED if decision == "defer" else ACK_CONFIRMED

    school = _resolve_school(request)
    key = owner_ack_key(school)
    stored = False
    if key is not None:
        try:
            from apps.schools.models import SchoolMembership

            # Only an actual owner of this school may acknowledge (defence in depth
            # — the card is owner-gated, but the endpoint must be too).
            if SchoolMembership.is_active_owner(request.user, school):
                from apps.runtime_blueprints.models import DashboardUserPreference

                pref, _created = DashboardUserPreference.objects.get_or_create(
                    user=request.user, defaults={"dashboard_layout": {}}
                )
                layout = dict(pref.dashboard_layout or {})
                layout[key] = ack
                pref.dashboard_layout = layout
                pref.save(update_fields=["dashboard_layout"])
                stored = True
        except (AttributeError, TypeError, ValueError, DatabaseError):
            stored = False

    wants_json = (
        request.headers.get("x-requested-with") == "XMLHttpRequest"
        or "application/json" in (request.headers.get("accept") or "")
    )
    if wants_json:
        return JsonResponse({"ok": stored, "decision": ack})
    next_url = (
        request.POST.get("next")
        or request.GET.get("next")
        or reverse("accounts:backend_dashboard")
    )
    return redirect(next_url)


@login_required
@require_POST
def mark_tour_complete(request):
    """Mark a first-run tour as completed for this user (persisted in DashboardUserPreference).

    The ``context`` (query or POST param) defaults to ``backend_dashboard`` for
    backward compatibility with the admin tour; per-role tenant landings pass
    ``?context=teacher_portal`` / ``parent_portal`` / ``student_portal`` so each
    role's first-run tour is remembered independently and never re-autostarts.
    """
    context = (
        request.POST.get("context") or request.GET.get("context") or "backend_dashboard"
    ).strip()
    if not re.fullmatch(r"[a-z0-9_]{1,40}", context):
        context = "backend_dashboard"
    try:
        from apps.runtime_blueprints.models import DashboardUserPreference

        pref, _ = DashboardUserPreference.objects.get_or_create(
            user=request.user, defaults={"dashboard_layout": {}}
        )
        layout = dict(pref.dashboard_layout or {})
        layout[f"tour_{context}_completed"] = True
        pref.dashboard_layout = layout
        pref.save(update_fields=["dashboard_layout"])
        return JsonResponse({"ok": True, "context": context})
    except (AttributeError, TypeError, ValueError, DatabaseError):
        return JsonResponse({"ok": False}, status=500)


@login_required
def onboarding_profile(request):
    """First-login profile setup — the second forced gate (after set-password) for
    an admin-provisioned temp-password account. Collects name + optional photo, then
    marks ``profile_setup_completed=True`` so OnboardingEnforcementMiddleware releases
    the user. A user who still owes a password change is sent to that step first; a
    fully set-up user is bounced to their dashboard so the page can't be re-entered."""
    from django import forms as dj_forms
    from django.contrib import messages
    from django.shortcuts import render
    from django.utils.translation import gettext as _

    from .models import User

    if getattr(request.user, "requires_password_change", False):
        return redirect("accounts:password_change")
    if getattr(request.user, "profile_setup_completed", True):
        return redirect("accounts:backend_dashboard")

    class OnboardingProfileForm(dj_forms.ModelForm):
        class Meta:
            model = User
            fields = ["first_name", "last_name", "profile_photo"]
            widgets = {
                "first_name": dj_forms.TextInput(
                    attrs={"class": "form-control", "autofocus": "autofocus"}
                ),
                "last_name": dj_forms.TextInput(attrs={"class": "form-control"}),
                "profile_photo": dj_forms.ClearableFileInput(
                    attrs={"class": "form-control", "accept": "image/*"}
                ),
            }

        def clean_first_name(self):
            value = (self.cleaned_data.get("first_name") or "").strip()
            if not value:
                raise dj_forms.ValidationError(_("Please enter your first name."))
            return value

        def clean_last_name(self):
            value = (self.cleaned_data.get("last_name") or "").strip()
            if not value:
                raise dj_forms.ValidationError(_("Please enter your last name."))
            return value

    if request.method == "POST":
        form = OnboardingProfileForm(request.POST, request.FILES, instance=request.user)
        if form.is_valid():
            user = form.save(commit=False)
            user.profile_setup_completed = True
            user.save()
            messages.success(request, _("Your profile is set up. Welcome aboard!"))
            return redirect("accounts:backend_dashboard")
    else:
        form = OnboardingProfileForm(instance=request.user)
    return render(request, "accounts/onboarding_profile.html", {"form": form})
