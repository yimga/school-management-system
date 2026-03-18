"""
Runtime constitution helpers for finance.
Use request.tenant_runtime.policy when available; otherwise policy_registry.get_effective_policy(school).
Use in views when calling get_gateway(school, method, policy=...) or get_platform_fee(school, method, amount, policy=...).
Aligns with EXECUTION_MAP_ALIGNMENT and REFACTOR_PATTERN_GRADEBOOK_AND_ADMISSIONS.
"""

from __future__ import annotations

from typing import Any, Dict


def get_policy_for_request(request) -> Dict[str, Any]:
    """
    Single read path for policy in request context.
    Prefer request.tenant_runtime.policy; fall back to policy_registry.get_effective_policy(school).
    Use when calling get_gateway(..., policy=...) or get_platform_fee(..., policy=...) from a view.
    """
    runtime = getattr(request, "tenant_runtime", None)
    if runtime is not None and getattr(runtime, "policy", None):
        return runtime.policy
    school = getattr(request, "school", None)
    if school is not None:
        from apps.policies.policy_registry import get_effective_policy

        return get_effective_policy(school)
    return {}
