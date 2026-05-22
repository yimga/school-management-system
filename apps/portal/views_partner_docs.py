"""Partner / interop documentation assistant surface (batch 1395)."""

from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, HttpResponseForbidden
from django.shortcuts import render
from django.urls import reverse

from apps.accounts.models import User


@login_required
def partner_documentation_assistant(request) -> HttpResponse:
    """Staff-only UI wrapping ``api:ai-interop-assistant`` (no duplicate gateway)."""
    role = (getattr(request.user, "role", None) or "").upper()
    if not (
        request.user.is_staff
        or request.user.is_superuser
        or role
        in (
            User.Role.ADMIN,
            User.Role.TEACHER,
            User.Role.LEADERSHIP,
            User.Role.PRINCIPAL,
        )
    ):
        return HttpResponseForbidden("Partner documentation assistant requires staff access.")

    api_url = ""
    interop_hub = ""
    try:
        api_url = reverse("api:ai-interop-assistant")
        interop_hub = reverse("accounts:district_lms_interop")
    except Exception:
        pass

    return render(
        request,
        "portal/partner_documentation_assistant.html",
        {
            "interop_api_url": api_url,
            "interop_hub_url": interop_hub,
            "ai_tier_hint": "cloud-or-rules",
        },
    )
