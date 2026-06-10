"""
Middleware: pin tenant boundary + wrap DB executes for the request lifetime.
"""

from __future__ import annotations

import logging

from django.db import connection
from django.utils.deprecation import MiddlewareMixin

from apps.tenancy.boundary_core_guard import (
    make_execute_wrapper,
    pin_tenant_boundary,
    unpin_tenant_boundary,
)

logger = logging.getLogger(__name__)


class TenantBoundaryCoreGuardMiddleware(MiddlewareMixin):
    """
    After ``TenantContextMiddleware`` resolves ``request.tenant_ctx``, pin
    ``school_id`` and enforce raw SQL parameter boundaries for the request.
    """

    def __call__(self, request):
        ctx = getattr(request, "tenant_ctx", None)
        school_id = getattr(ctx, "school_id", None) if ctx else None
        host = getattr(ctx, "host", "") if ctx else ""
        token = None
        if school_id:
            token = pin_tenant_boundary(school_id=school_id, host=host)
        wrapper = make_execute_wrapper()
        try:
            with connection.execute_wrapper(wrapper):
                return self.get_response(request)
        finally:
            if token:
                unpin_tenant_boundary(token)
