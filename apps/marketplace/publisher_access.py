"""Verified publisher access on the control-plane (manager host)."""

from __future__ import annotations

from functools import wraps

from django.http import HttpResponseForbidden

from apps.schools.control_plane import _is_super_surface, user_has_control_plane_access


def publisher_for_user(user):
    if user is None or not getattr(user, "email", ""):
        return None
    try:
        from apps.marketplace.models import PublisherOrganization
    except ImportError:
        return None
    return (
        PublisherOrganization.objects.filter(
            verified_contact_email=user.email,
            verification_status=PublisherOrganization.VerificationStatus.VERIFIED,
        )
        .order_by("pk")
        .first()
    )


def user_has_verified_publisher_access(user) -> bool:
    return publisher_for_user(user) is not None


def require_verified_publisher_with_host(view_func):
    """Manager/super surface: verified publisher OR platform operator."""

    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if not _is_super_surface(request):
            return HttpResponseForbidden(
                "Control-plane surface required (manager host or /super/)."
            )
        if not getattr(request, "user", None) or not request.user.is_authenticated:
            from django.contrib.auth.views import redirect_to_login

            return redirect_to_login(request.get_full_path())
        if user_has_control_plane_access(request.user):
            return view_func(request, *args, **kwargs)
        if user_has_verified_publisher_access(request.user):
            return view_func(request, *args, **kwargs)
        return HttpResponseForbidden("Verified publisher or operator access required.")

    return _wrapped
