"""
§2.3 AI permission model by role/task/tenant.
Call before invoking AI gateway; enforces auth, role, and optional tenant/plan checks.
"""
from __future__ import annotations

from typing import Any

# Task types that require staff (admin/copilot/setup)
STAFF_ONLY_TASKS = frozenset({
    "admin_copilot",
    "config_explain",
    "migration_mapping",
    "migration_fingerprint",
    "migration_parity",
    "policy_explain",
})

# Tenant Studio / district surfaces: staff OR configured tenant role with a school context
TENANT_STUDIO_AI_TASKS = frozenset({
    "interop_assistant",
    "runtime_config_explain",
    "studio_os_assistant",
})

# Fleet / control-plane only (no tenant PII in prompts; still rate-limited)
FLEET_STAFF_AI_TASKS = frozenset({
    "observability_assistant",
    "trust_compliance_assistant",
})

# Billing / usage narrative: staff or finance-capable tenant role with school
BILLING_USAGE_AI_TASKS = frozenset({
    "billing_usage_explain",
})


def _user_is_tenant_config_role(user: Any) -> bool:
    role = getattr(user, "role", None) or ""
    return role in {
        "ADMIN",
        "IT_ADMIN",
        "LEADERSHIP",
        "PROPRIETOR",
        "PRINCIPAL",
        "VICE_PRINCIPAL",
    }


def _user_is_finance_role(user: Any) -> bool:
    role = getattr(user, "role", None) or ""
    return role in {
        "BURSAR",
        "FINANCE_STAFF",
        "ACCOUNTANT",
        "ADMIN",
        "PROPRIETOR",
        "LEADERSHIP",
    }


def _control_plane_operator(user: Any) -> bool:
    try:
        from apps.schools.control_plane import user_has_control_plane_access

        return user_has_control_plane_access(user)
    except ImportError:
        return False


def _staff_or_super(user: Any) -> bool:
    return bool(getattr(user, "is_staff", False) or getattr(user, "is_superuser", False))


def _staff_super_or_control_plane(user: Any) -> bool:
    """Manager operators may be SUPERADMIN without is_staff; align with control_plane.py."""
    return _staff_or_super(user) or _control_plane_operator(user)


def get_ai_permission_for_user(
    user: Any,
    task_type: str,
    school: Any = None,
) -> bool:
    """
    Return True if user is allowed to run the given AI task in this tenant/school context.
    §2.3: permission model by role/task/tenant; deepen with plan/entitlement checks as needed.
    """
    if user is None or not getattr(user, "is_authenticated", False):
        return False
    task = (task_type or "").strip().lower()
    if task in STAFF_ONLY_TASKS:
        if not _staff_super_or_control_plane(user):
            return False
    if task in TENANT_STUDIO_AI_TASKS:
        if _staff_super_or_control_plane(user):
            return True
        if school is not None and _user_is_tenant_config_role(user):
            return True
        return False
    if task in FLEET_STAFF_AI_TASKS:
        return _staff_super_or_control_plane(user)
    if task in BILLING_USAGE_AI_TASKS:
        if _staff_super_or_control_plane(user):
            return True
        if school is not None and _user_is_finance_role(user):
            return True
        return False
    return True
