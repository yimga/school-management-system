"""
Portal "hat" helpers for dual-role users (e.g. teacher who is also a parent).

Use these to decide if a user can act as Teacher or Parent in the portal.
Effective portal role (session) drives sidebar and redirect; these helpers
drive access control and UI visibility.
"""

from django.core.exceptions import ObjectDoesNotExist
from django.db import DatabaseError
from apps.siteconfig.config_service import get_effective_site_settings
from django.contrib.auth import get_user_model

User = get_user_model()

# Session key and allowed values for active portal context when user has both hats.
ACTIVE_PORTAL_ROLE_KEY = "active_portal_role"
ALLOWED_PORTAL_ROLES = ("TEACHER", "PARENT")
PORTAL_ROLE_SOFT_FAILURES = (
    AttributeError,
    DatabaseError,
    ImportError,
    LookupError,
    ObjectDoesNotExist,
    TypeError,
    ValueError,
)


def has_teacher_hat(user) -> bool:
    """
    True if the user can act as a teacher in the portal (has a TeacherProfile).
    """
    if not user or not getattr(user, "is_authenticated", False):
        return False
    from apps.people.models import TeacherProfile

    # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
    return TeacherProfile.objects.filter(user=user).exists()


def has_parent_hat(user) -> bool:
    """
    True if the user can act as a parent in the portal (has at least one StudentGuardian link).
    """
    if not user or not getattr(user, "is_authenticated", False):
        return False
    from apps.people.models import StudentGuardian

    return StudentGuardian.objects.filter(guardian_user=user).exists()


def _has_teacher_hat_cached(request):
    """Use request cache if set to avoid repeated DB; otherwise call has_teacher_hat."""
    if request and getattr(request, "_portal_teacher_hat", None) is not None:
        return request._portal_teacher_hat
    return has_teacher_hat(getattr(request, "user", None))


def _has_parent_hat_cached(request):
    """Use request cache if set to avoid repeated DB; otherwise call has_parent_hat."""
    if request and getattr(request, "_portal_parent_hat", None) is not None:
        return request._portal_parent_hat
    return has_parent_hat(getattr(request, "user", None))


def get_effective_portal_role(request) -> str:
    """
    Return the portal role to use for sidebar and redirect when user has one or both hats.

    - If user has both hats and session has a valid active_portal_role, use that.
    - Else if session empty and user has both hats, restore from UserPreference.last_portal_role and set session.
    - Otherwise use the user's primary role (user.role), normalized to uppercase.

    Use this only for UI (sidebar, redirect). Access control should use has_teacher_hat
    / has_parent_hat and object-level checks (guardian_links, teacher_scope).
    """
    if not request or not getattr(request.user, "is_authenticated", False):
        return ""
    user = request.user
    # Context processors run on every render — including error pages that may be
    # produced before SessionMiddleware attaches request.session — so never assume
    # it exists. (get_nav_portal_role guards the same way; without this its guard is
    # defeated, since it calls this function first.)
    session = getattr(request, "session", None)
    session_role = (
        (session.get(ACTIVE_PORTAL_ROLE_KEY) if session is not None else "") or ""
    ).strip().upper()
    if session_role in ALLOWED_PORTAL_ROLES:
        if session_role == "TEACHER" and _has_teacher_hat_cached(request):
            return "TEACHER"
        if session_role == "PARENT" and _has_parent_hat_cached(request):
            return "PARENT"
    # Restore from saved preference when session empty and user has both hats
    has_teacher = _has_teacher_hat_cached(request)
    has_parent = _has_parent_hat_cached(request)
    if has_teacher and has_parent:
        try:
            from apps.siteconfig.models import UserPreference

            pref = (
                UserPreference.objects.filter(user=user)
                .only("last_portal_role")
                .first()
            )
            saved = (getattr(pref, "last_portal_role", "") or "").strip().upper()
            if saved in ALLOWED_PORTAL_ROLES:
                request.session[ACTIVE_PORTAL_ROLE_KEY] = saved
                return saved
            # No valid user preference: fall back to site-level default
            # config-resolver-allow: unit test patches this module symbol targeting this call path (resolver-failure fallback)
            site = get_effective_site_settings(request=request)
            default_role = (
                (getattr(site, "default_portal_role_dual_role", "") or "")
                .strip()
                .upper()
            )
            if default_role in ALLOWED_PORTAL_ROLES:
                request.session[ACTIVE_PORTAL_ROLE_KEY] = default_role
                if pref is None:
                    pref = UserPreference(user=user, last_portal_role=default_role)
                    pref.save()
                else:
                    pref.last_portal_role = default_role
                    pref.save(update_fields=["last_portal_role", "updated_at"])
                return default_role
        except PORTAL_ROLE_SOFT_FAILURES:
            pass
    return (getattr(user, "role", "") or "").upper()


def get_nav_portal_role(request) -> str:
    """Role for sidebar, top nav, and post-login redirect.

    Honors explicit session hat (``active_portal_role``) for PARENT/STUDENT even when
    the user's primary role is staff/admin — matches family-surface UX expectations.
    """
    if not request or not getattr(getattr(request, "user", None), "is_authenticated", False):
        return ""
    user = request.user
    primary_role = (getattr(user, "role", "") or "").upper()
    role = get_effective_portal_role(request) or primary_role
    session_hat = ""
    if getattr(request, "session", None) is not None:
        session_hat = (request.session.get(ACTIVE_PORTAL_ROLE_KEY) or "").strip().upper()
    if session_hat in (User.Role.PARENT, User.Role.STUDENT):
        return session_hat
    if role in (User.Role.PARENT, User.Role.STUDENT, User.Role.TEACHER):
        return role
    return role or primary_role
