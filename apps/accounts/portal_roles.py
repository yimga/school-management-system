"""
Portal "hat" helpers for dual-role users (e.g. teacher who is also a parent).

Use these to decide if a user can act as Teacher or Parent in the portal.
Effective portal role (session) drives sidebar and redirect; these helpers
drive access control and UI visibility.
"""
from django.contrib.auth import get_user_model

User = get_user_model()

# Session key and allowed values for active portal context when user has both hats.
ACTIVE_PORTAL_ROLE_KEY = "active_portal_role"
ALLOWED_PORTAL_ROLES = ("TEACHER", "PARENT")


def has_teacher_hat(user) -> bool:
    """
    True if the user can act as a teacher in the portal (has a TeacherProfile).
    """
    if not user or not getattr(user, "is_authenticated", False):
        return False
    from apps.people.models import TeacherProfile
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
    session_role = (request.session.get(ACTIVE_PORTAL_ROLE_KEY) or "").strip().upper()
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
            pref = UserPreference.objects.filter(user=user).only("last_portal_role").first()
            saved = (getattr(pref, "last_portal_role", "") or "").strip().upper()
            if saved in ALLOWED_PORTAL_ROLES:
                request.session[ACTIVE_PORTAL_ROLE_KEY] = saved
                return saved
            # No valid user preference: fall back to site-level default
            from apps.siteconfig.models import SiteSettings
            site = SiteSettings.get_solo()
            default_role = (getattr(site, "default_portal_role_dual_role", "") or "").strip().upper()
            if default_role in ALLOWED_PORTAL_ROLES:
                request.session[ACTIVE_PORTAL_ROLE_KEY] = default_role
                if pref is None:
                    pref = UserPreference(user=user, last_portal_role=default_role)
                    pref.save()
                else:
                    pref.last_portal_role = default_role
                    pref.save(update_fields=["last_portal_role", "updated_at"])
                return default_role
        except Exception:
            pass
    return (getattr(user, "role", "") or "").upper()
