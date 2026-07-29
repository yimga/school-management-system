"""
Central permission helpers for tenant marketplace (install, activate, scopes).

``user_passes_test`` wrappers stay in views; this module is the single source of truth.
"""

from __future__ import annotations

from functools import wraps
from typing import Any, Callable

from django.core.exceptions import PermissionDenied


def tenant_may_manage_marketplace(user: Any, *, school: Any = None) -> bool:
    """
    Tenant: school owners, admin-like roles, or staff/superuser may manage apps and scopes.

    When ``school`` is provided, an active ``SchoolMembership.is_school_owner`` for that
    school also passes — owners provisioned as ``role=PROPRIETOR`` (or without ADMIN) were
    incorrectly denied when the gate only checked role strings.
    """
    if not getattr(user, "is_authenticated", False):
        return False
    if user.is_superuser or user.is_staff:
        return True
    role = (getattr(user, "role", "") or "").upper()
    try:
        from apps.accounts.auth_backends_role_perms import ADMIN_LIKE_ROLES

        if role in ADMIN_LIKE_ROLES or role == "IT_ADMIN":
            return True
    except ImportError:
        if role in ("ADMIN", "IT_ADMIN", "LEADERSHIP", "PROPRIETOR", "PRINCIPAL"):
            return True
    if school is not None:
        try:
            from apps.accounts.views_owner_console import is_school_owner

            if is_school_owner(user, school):
                return True
        except ImportError:
            pass
    return False


def tenant_marketplace_manage_required(view_func: Callable | None = None):
    """Request-scoped marketplace manage gate (school owner + role aware)."""

    def decorator(fn: Callable):
        @wraps(fn)
        def _inner(request, *args, **kwargs):
            if not tenant_may_manage_marketplace(
                getattr(request, "user", None),
                school=getattr(request, "school", None),
            ):
                raise PermissionDenied
            return fn(request, *args, **kwargs)

        return _inner

    if view_func is not None:
        return decorator(view_func)
    return decorator
