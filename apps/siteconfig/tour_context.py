"""Resolve guided-tour API context from user role and requested surface."""

from __future__ import annotations

# Roles that use backend command center (subset get leadership/ops variants).
# This module is the SOT for tour-context role mapping — strings declared here
# drive which guided-tour catalog key a backend dashboard loads.
_BACKEND_ROLES = frozenset(
    {
        "ADMIN",  # role-string-allow: tour-context-role-map SOT
        "SUPERADMIN",  # role-string-allow: tour-context-role-map SOT
        "PRINCIPAL",  # role-string-allow: tour-context-role-map SOT
        "PROPRIETOR",  # role-string-allow: tour-context-role-map SOT
        "IT_ADMIN",  # role-string-allow: tour-context-role-map SOT
        "LEADERSHIP",  # role-string-allow: tour-context-role-map SOT
        "SECRETARY",  # role-string-allow: tour-context-role-map SOT
        "ACCOUNTANT",  # role-string-allow: tour-context-role-map SOT
    }
)
_LEADERSHIP_ROLES = frozenset({"PRINCIPAL", "PROPRIETOR", "LEADERSHIP"})  # role-string-allow: tour-context-role-map SOT
_OPS_ROLES = frozenset({"IT_ADMIN", "SECRETARY"})  # role-string-allow: tour-context-role-map SOT


def user_role_upper(user) -> str:
    return (getattr(user, "role", None) or "").strip().upper()


def resolve_backend_tour_context(user) -> str:
    """
    Per-role backend dashboard tour context.

    Teachers/parents/students use portal-specific tours, not backend autostart.
    """
    if not getattr(user, "is_authenticated", False):
        return "backend_dashboard"
    if getattr(user, "is_superuser", False):
        return "backend_dashboard_admin"
    role = user_role_upper(user)
    if role in ("TEACHER", "PARENT", "STUDENT"):  # role-string-allow: tour-context-role-map SOT
        return ""
    if role in _LEADERSHIP_ROLES:
        return "backend_dashboard_leadership"
    if role in _OPS_ROLES:
        return "backend_dashboard_operations"
    if role in _BACKEND_ROLES or role == "ADMIN":  # role-string-allow: tour-context-role-map SOT
        return "backend_dashboard_admin"
    return "backend_dashboard_admin"


def normalize_tour_context(request, raw_context: str) -> str:
    """
    Map generic ``backend_dashboard`` to a role-specific catalog key when needed.
    """
    ctx = (raw_context or "backend_dashboard").strip()
    if ctx == "backend_dashboard" and getattr(request, "user", None):
        role_ctx = resolve_backend_tour_context(request.user)
        if role_ctx:
            return role_ctx
    return ctx
