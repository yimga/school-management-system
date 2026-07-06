"""
Centralized RBAC helpers for the compliance app.
Use these for dashboard, reporting, and API views that require staff/admin access.
"""

from apps.accounts.utils import get_user_role


def is_admin_or_staff(user):
    """
    Check if user is allowed to access compliance dashboard and admin compliance features.
    Returns True for superuser, staff, or role in ADMIN, LEADERSHIP.
    """
    if not user or not user.is_authenticated:
        return False
    role = get_user_role(user)
    if user.is_superuser or user.is_staff or role in ("ADMIN", "LEADERSHIP"):
        return True
    # RBAC-completion: ADDITIVELY admit holders of the granular
    # `compliance.manage` code (e.g. a custom DPO/registrar role an owner
    # grants) — appropriate for these management CBVs. Nobody who had access
    # before loses it. Guarded so a DB hiccup fails closed, not open.
    try:
        return bool(user.has_feature_permission("compliance.manage"))
    except Exception:
        return False
