"""
Out of Office / Delegation: profile views for listing, creating, editing, revoking
delegations and viewing the "While You Were Away" catch-up log.
"""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render, get_object_or_404
from django.utils import timezone
from django.http import HttpResponseForbidden

from apps.platform_runtime.helpers import get_effective_site_settings
from .models import Delegation, DelegationActionLog
from .forms import DelegationForm
from .delegation import (
    user_can_create_delegation,
    get_active_delegation_for_delegate,
)


@login_required
def my_delegations(request):
    """List current user's delegations (as delegator) and link to add/catch-up."""
    delegations_made = (
        Delegation.objects.filter(delegator=request.user)
        .select_related("delegate")
        .order_by("-start_date")
    )
    active_as_delegate = get_active_delegation_for_delegate(request.user)
    can_create = user_can_create_delegation(request.user)

    context = {
        "delegations_made": delegations_made,
        "active_as_delegate": active_as_delegate,
        "can_create": can_create,
    }
    return render(request, "accounts/my_delegations.html", context)


@login_required
def delegation_add(request):
    """Create a new delegation (current user = delegator)."""
    if not user_can_create_delegation(request.user):
        return HttpResponseForbidden("Your role cannot create delegations.")

    if request.method == "POST":
        form = DelegationForm(request.user, request.POST)
        if form.is_valid():
            scope = form.cleaned_data.get("scope") or []
            d = Delegation.objects.create(
                delegator=request.user,
                delegate=form.cleaned_data["delegate"],
                start_date=form.cleaned_data["start_date"],
                end_date=form.cleaned_data["end_date"],
                scope=scope,
                reason=form.cleaned_data.get("reason", ""),
                notes=form.cleaned_data.get("notes", ""),
                created_by=request.user,
            )
            if d.start_date <= timezone.now():
                try:
                    from apps.people.badge_services import (
                        create_acting_badge_for_delegation,
                    )

                    create_acting_badge_for_delegation(d)
                except (ImportError, AttributeError, TypeError, ValueError):
                    pass
                try:
                    site = get_effective_site_settings(request=request)
                    notify = getattr(site, "delegation_notify_delegate_on_start", "off")
                    if notify in ("email", "both") and d.delegate.email:
                        from django.core.mail import send_mail
                        from django.conf import settings as django_settings

                        send_mail(
                            subject="Delegation started: you are acting on behalf of %s"
                            % d.delegator.get_full_name()
                            or d.delegator.username,
                            message="You have been assigned to act on behalf of %s until %s."
                            % (
                                d.delegator.get_full_name() or d.delegator.username,
                                d.effective_end_date.date(),
                            ),
                            from_email=getattr(
                                django_settings,
                                "DEFAULT_FROM_EMAIL",
                                "noreply@school.local",
                            ),
                            recipient_list=[d.delegate.email],
                            fail_silently=True,
                        )
                except (OSError, ConnectionError, AttributeError, TypeError):
                    pass
            messages.success(
                request,
                "Delegation created. Your delegate can now act on your behalf for the selected scope.",
            )
            return redirect("accounts:my_delegations")
    else:
        form = DelegationForm(request.user)

    return render(
        request, "accounts/delegation_form.html", {"form": form, "is_edit": False}
    )


@login_required
def delegation_edit(request, pk):
    """Edit an existing delegation (only delegator; only end_date, scope, notes)."""
    delegation = get_object_or_404(Delegation, pk=pk, delegator=request.user)
    if not delegation.is_active:
        messages.warning(request, "This delegation is no longer active.")
        return redirect("accounts:my_delegations")

    if request.method == "POST":
        # Build POST with delegate/start_date so form validates (disabled fields are not in POST)
        post = request.POST.copy()
        post.setdefault("delegate", str(delegation.delegate_id))
        post.setdefault("start_date", delegation.start_date.strftime("%Y-%m-%dT%H:%M"))
        form = DelegationForm(request.user, post)
        if form.is_valid():
            delegation.scope = form.cleaned_data.get("scope") or []
            delegation.end_date = form.cleaned_data["end_date"]
            delegation.reason = form.cleaned_data.get("reason", "")
            delegation.notes = form.cleaned_data.get("notes", "")
            delegation.save()
            messages.success(request, "Delegation updated.")
            return redirect("accounts:my_delegations")
    else:
        form = DelegationForm(
            request.user,
            initial={
                "delegate": delegation.delegate,
                "start_date": delegation.start_date,
                "end_date": delegation.end_date,
                "scope": delegation.scope if isinstance(delegation.scope, list) else [],
                "reason": delegation.reason or "",
                "notes": delegation.notes or "",
            },
        )
        form.fields["delegate"].disabled = True
        form.fields["start_date"].disabled = True

    return render(
        request,
        "accounts/delegation_form.html",
        {"form": form, "delegation": delegation, "is_edit": True},
    )


@login_required
def delegation_revoke(request, pk):
    """Set is_active=False on the delegation (only delegator)."""
    delegation = get_object_or_404(Delegation, pk=pk, delegator=request.user)
    if request.method == "POST":
        delegation.is_active = False
        delegation.save()
        try:
            from apps.people.badge_services import revoke_acting_badges_for_delegation

            revoke_acting_badges_for_delegation(delegation)
        except (ImportError, AttributeError, TypeError, ValueError):
            pass
        messages.success(
            request, "Delegation ended. Your delegate can no longer act on your behalf."
        )
        return redirect("accounts:my_delegations")
    return redirect("accounts:my_delegations")


@login_required
def delegation_catch_up(request):
    """While You Were Away: list actions performed by delegates on behalf of the current user."""
    logs = (
        DelegationActionLog.objects.filter(acting_for=request.user)
        .select_related("actor", "delegation")
        .order_by("-created_at")[:200]
    )
    return render(request, "accounts/delegation_catch_up.html", {"action_logs": logs})
