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
        if not getattr(user, "is_staff", False):
            return False
    # Optional: check feature flag or entitlement for school (e.g. AI_SETUP_RECOMMEND enabled for plan)
    # if school and not get_effective_flags(school).get("ai_setup_recommend", False): return False
    return True
