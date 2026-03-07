"""
Platform runtime: unified TenantRuntime per request.
Single entry point for tenant identity + policy + workflow/dashboard resolution.
"""
from .contracts import TenantRuntime
from .runtime_resolver import build_tenant_runtime

__all__ = ["TenantRuntime", "build_tenant_runtime"]
