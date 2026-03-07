"""
Runtime constitution helpers for evals (Gradebook).
Use request.tenant_runtime.policy when available; otherwise policy_registry.get_effective_policy(school).
Replicate this pattern in other modules (e.g. people/Admissions) for consistent injection.
"""
from __future__ import annotations

from typing import Any, Dict, Optional


def get_policy_for_request(request) -> Dict[str, Any]:
    """
    Single read path for policy in request context (Execution map / runtime constitution).
    Prefer request.tenant_runtime.policy; fall back to policy_registry.get_effective_policy(school).
    Use in views instead of ad-hoc get_effective_policy(school) when request is available.
    """
    runtime = getattr(request, "tenant_runtime", None)
    if runtime is not None and getattr(runtime, "policy", None):
        return runtime.policy
    school = getattr(request, "school", None)
    if school is not None:
        from apps.policies.policy_registry import get_effective_policy
        return get_effective_policy(school)
    return {}


def get_grade_approval_policy_for_request(request) -> Dict[str, Any]:
    """Grade approval slice from policy for this request. Uses get_policy_for_request(request)."""
    policy = get_policy_for_request(request)
    return (policy.get("grade_approval") or {}).copy()
