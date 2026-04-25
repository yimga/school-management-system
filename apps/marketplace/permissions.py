"""
Central permission helpers for tenant marketplace (install, activate, scopes).

``user_passes_test`` wrappers stay in views; this module is the single source of truth.
"""

from __future__ import annotations

from typing import Any


def tenant_may_manage_marketplace(user: Any) -> bool:
    """
    Tenant: only ADMIN, IT_ADMIN, LEADERSHIP, or staff/superuser can manage apps and scopes.
    """
    if not getattr(user, "is_authenticated", False):
        return False
    if user.is_superuser or user.is_staff:
        return True
    role = (getattr(user, "role", "") or "").upper()
    return role in ("ADMIN", "IT_ADMIN", "LEADERSHIP")
