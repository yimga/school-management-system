"""School context profile session helpers (global governance Phase 3C)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.db.models import QuerySet

from apps.governance.models import SchoolContextProfile

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractBaseUser
    from django.http import HttpRequest

ACTIVE_PROFILE_SESSION_KEY = "rmc_active_context_profile_id"


def list_profiles(user: "AbstractBaseUser | None") -> QuerySet[SchoolContextProfile]:
    """Return all context profiles for ``user``, newest default first."""
    if user is None or not getattr(user, "is_authenticated", False):
        return SchoolContextProfile.objects.none()
    return (
        # tenant-isolation-allow: school-context-profile-scoped-via-user-fk-session-bound
        SchoolContextProfile.objects.filter(user=user)
        .select_related("school")
        .order_by("-is_default", "school__name", "label")
    )


def _fallback_profile(
    user: "AbstractBaseUser",
    school: object | None = None,
) -> SchoolContextProfile | None:
    # tenant-isolation-allow: school-context-profile-scoped-via-user-fk-session-bound
    qs = SchoolContextProfile.objects.filter(user=user)
    if school is not None and getattr(school, "pk", None):
        scoped = qs.filter(school=school)
        return (
            scoped.filter(is_default=True).first()
            or scoped.order_by("label").first()
        )
    return qs.filter(is_default=True).first() or qs.order_by("school__name", "label").first()


def resolve_active_profile(request: "HttpRequest") -> SchoolContextProfile | None:
    """
    Resolve the active context profile from session, with school-scoped fallback.

    Honors ``request.session[ACTIVE_PROFILE_SESSION_KEY]`` when the profile
    belongs to ``request.user``. Otherwise picks the default profile for
    ``request.school`` when bound.
    """
    user = getattr(request, "user", None)
    if user is None or not getattr(user, "is_authenticated", False):
        return None

    raw = request.session.get(ACTIVE_PROFILE_SESSION_KEY)
    if raw is not None:
        try:
            profile_id = int(raw)
        except (TypeError, ValueError):
            profile_id = None
        if profile_id:
            profile = (
                # tenant-isolation-allow: school-context-profile-scoped-via-user-fk-session-bound
                SchoolContextProfile.objects.filter(pk=profile_id, user=user)
                .select_related("school")
                .first()
            )
            if profile is not None:
                return profile

    return _fallback_profile(user, getattr(request, "school", None))


def set_active_profile_session(
    request: "HttpRequest",
    profile_id: int,
) -> SchoolContextProfile:
    """Persist ``profile_id`` in session after verifying ownership."""
    user = getattr(request, "user", None)
    if user is None or not getattr(user, "is_authenticated", False):
        raise PermissionError("Authenticated user required to set context profile.")

    # tenant-isolation-allow: school-context-profile-scoped-via-user-fk-session-bound
    profile = SchoolContextProfile.objects.filter(pk=profile_id, user=user).first()
    if profile is None:
        raise ValueError("Context profile not found for this user.")

    request.session[ACTIVE_PROFILE_SESSION_KEY] = profile.pk
    request.session.modified = True
    return profile
