"""
Attach request.tenant_runtime (TenantRuntime) after tenant_ctx is set.
Must run after TenantContextMiddleware.
"""
from django.utils.deprecation import MiddlewareMixin

from .runtime_resolver import build_tenant_runtime


class TenantRuntimeMiddleware(MiddlewareMixin):
    """
    Set request.tenant_runtime (TenantRuntime: identity + policy + workflow/dashboard).
    Run after TenantContextMiddleware so request.tenant_ctx is available.
    """

    def process_request(self, request):
        tenant_ctx = getattr(request, "tenant_ctx", None)
        if tenant_ctx is None:
            request.tenant_runtime = None
            return None
        request.tenant_runtime = build_tenant_runtime(tenant_ctx, request=request)
        return None
