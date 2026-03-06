"""
Canonical entry point: get_tenant_blueprint(request), policy(name).evaluate(context).
Modules must not read features_json / settings_json directly; use this registry.
"""
from typing import Any, Dict, Optional

from apps.policies.resolver import get_effective_policy, get_tenant_blueprint as _get_tenant_blueprint


def get_tenant_blueprint(request) -> Dict[str, Any]:
    """Returns a normalized blueprint for the active tenant (school)."""
    school = getattr(request, "school", None)
    return _get_tenant_blueprint(school)


def get_policy_for_request(request) -> Dict[str, Any]:
    """Wrapper that returns policy for the request's tenant. Same as get_tenant_blueprint(request)."""
    return get_tenant_blueprint(request)


def get_resolved_env(tenant, user=None) -> Dict[str, Any]:
    """
    TenantPolicyService.get_resolved_env(tenant, user) equivalent.
    Returns resolved behavior (labels, features, workflows, grading, etc.) for this tenant.
    """
    return get_effective_policy(tenant, user=user)


def policy(name: str):
    """
    Return a policy evaluator for the given policy name (e.g. 'admissions', 'gradebook').
    Usage: registry.policy('admissions').evaluate(context) -> allowed actions, required fields, etc.
    """
    class _PolicyEvaluator:
        def __init__(self, policy_name: str):
            self.policy_name = policy_name

        def evaluate(self, context: Dict[str, Any]) -> Dict[str, Any]:
            school = context.get("school") or context.get("tenant")
            policy_dict = get_effective_policy(school, user=context.get("user"))
            # Return the slice relevant to this policy name
            policies = policy_dict.get("workflows", {}) or policy_dict.get("policies", {})
            if isinstance(policies, dict) and self.policy_name in policies:
                return policies[self.policy_name]
            return {"enabled": True, "policy": policy_dict}
    return _PolicyEvaluator(name)
