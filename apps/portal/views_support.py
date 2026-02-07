from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.shortcuts import redirect, render
from django.utils.http import url_has_allowed_host_and_scheme

from apps.accounts.models import User
from apps.communication.models import Message

from .forms_support import SupportRequestForm


def _pick_support_owner() -> User | None:
    preferred_roles = [
        User.Role.IT_ADMIN,
    ]
    fallback_roles = [
        User.Role.ADMIN,
        User.Role.SUPERADMIN,
        User.Role.LEADERSHIP,
    ]

    qs = User.objects.filter(Q(role__in=preferred_roles) | Q(roles__code__in=preferred_roles)).distinct()
    if qs.exists():
        return qs.order_by("id").first()

    qs = User.objects.filter(Q(role__in=fallback_roles) | Q(roles__code__in=fallback_roles)).distinct()
    if qs.exists():
        return qs.order_by("id").first()

    qs = User.objects.filter(Q(is_superuser=True) | Q(is_staff=True)).distinct()
    return qs.order_by("id").first()


@login_required
def support_request(request):
    next_url = request.GET.get("next") or request.POST.get("next") or ""
    if next_url and not url_has_allowed_host_and_scheme(next_url, {request.get_host()}):
        next_url = ""

    initial = {}
    category = request.GET.get("type") or request.POST.get("category")
    if category:
        initial["category"] = category.upper()

    form = SupportRequestForm(request.POST or None, initial=initial)
    if request.method == "POST" and form.is_valid():
        recipient = _pick_support_owner()
        if not recipient:
            messages.error(request, "No support team is configured yet. Please contact an administrator.")
        else:
            subject_prefix = "[Support]" if form.cleaned_data["category"] == "SUPPORT" else "[Feedback]"
            subject = f"{subject_prefix} {form.cleaned_data['subject']}"
            body = (
                f"From: {request.user.get_full_name()} ({request.user.username})\n"
                f"Role: {request.user.role}\n"
                f"Email: {request.user.email or 'N/A'}\n"
                f"Path: {request.path}\n"
                f"Next: {next_url or 'N/A'}\n\n"
                f"{form.cleaned_data['message']}"
            )
            Message.objects.create(
                sender=request.user,
                recipient=recipient,
                subject=subject,
                body=body,
            )
            messages.success(request, "Thanks! Your message has been sent to the support team.")
            if next_url:
                return redirect(next_url)
            return redirect("portal:portal_home")

    return render(
        request,
        "portal/support_request.html",
        {
            "form": form,
            "next_url": next_url,
        },
    )
