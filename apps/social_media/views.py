"""Tenant-scoped proud campus feed surfaces (React island hosts)."""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from django.shortcuts import render
from django.urls import reverse

from apps.accounts.decorators import role_required

User = get_user_model()


@login_required
@role_required(
    User.Role.ADMIN,
    User.Role.IT_ADMIN,
    User.Role.LEADERSHIP,
    User.Role.TEACHER,
)
def proud_campus_feed(request):
    """Operator-facing social feed grid + optional moderation queue."""
    school = getattr(request, "school", None)
    if not school:
        return HttpResponseForbidden("School context required.")

    feed_url = reverse("api_v1:social-feed")
    moderation_url = reverse("api_v1:social-moderation-list")
    role = (getattr(request.user, "role", "") or "").upper()
    show_moderation = request.user.is_staff or role in (
        User.Role.ADMIN,
        User.Role.IT_ADMIN,
        User.Role.LEADERSHIP,
    )

    return render(
        request,
        "social_media/proud_campus_feed.html",
        {
            "feed_url": feed_url,
            "moderation_url": moderation_url,
            "show_moderation": show_moderation,
        },
    )
