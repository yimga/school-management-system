"""
Centralized RBAC helpers for the compliance app.
Use these for dashboard, reporting, and API views that require staff/admin access.
"""


def is_admin_or_staff(user):
    """
    Check if user is allowed to access compliance dashboard and admin compliance features.
    Returns True for superuser, staff, or role in ADMIN, LEADERSHIP.
    """
    if not user or not user.is_authenticated:
        return False
    role = (getattr(user, "role", "") or "").upper()
    return user.is_superuser or user.is_staff or role in ("ADMIN", "LEADERSHIP")
