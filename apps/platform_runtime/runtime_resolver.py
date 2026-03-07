"""
Build TenantRuntime from request (tenant_ctx + school + policy).
Used by middleware to set request.tenant_runtime.
"""
from __future__ import annotations

from typing import Any, Optional

from apps.tenancy.context import TenantContext

from .contracts import TenantRuntime


def _school_from_request(request) -> Any:
    """School from request.school (RLS) or request.tenant.school (schema-per-tenant)."""
    school = getattr(request, "school", None)
    if school is not None:
        return school
    tenant = getattr(request, "tenant", None)
    if tenant is not None and hasattr(tenant, "school"):
        return getattr(tenant, "school", None)
    return None


def build_tenant_runtime(
    tenant_ctx: TenantContext,
    request: Optional[Any] = None,
    *,
    school: Optional[Any] = None,
    policy: Optional[dict] = None,
) -> TenantRuntime:
    """
    Build a TenantRuntime for the current request.
    Call from middleware after tenant_ctx is set; pass request so school and policy can be resolved.
    """
    if school is None and request is not None:
        school = _school_from_request(request)
    if policy is None and school is not None:
        try:
            from apps.policies.policy_registry import get_effective_policy
            user = getattr(request, "user", None) if request is not None else None
            policy = get_effective_policy(school, user=user)
        except Exception:
            policy = {}
    if policy is None:
        policy = {}

    runtime = TenantRuntime(
        tenant_ctx=tenant_ctx,
        policy=policy,
        _school=school,
    )
    return runtime
