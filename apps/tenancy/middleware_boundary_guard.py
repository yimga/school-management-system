"""
Middleware: pin tenant boundary + wrap DB executes for the request lifetime.
"""

from __future__ import annotations

import logging

from django.db import connection
from django.http import HttpResponseForbidden, JsonResponse
from django.utils.deprecation import MiddlewareMixin

from apps.tenancy.boundary_core_guard import (
    make_execute_wrapper,
    pin_tenant_boundary,
    unpin_tenant_boundary,
)
from apps.tenancy.exceptions import SecurityIsolationException

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

    def process_exception(self, request, exception):
        """A boundary refusal is a 403, not a crash.

        ``SecurityIsolationException`` is raised by ``boundary_core_guard`` when a
        query crosses the pinned tenant. Until now NOTHING converted it to a
        response -- it was raised in that module, caught only inside that module
        and its own tests, and reached the handler unhandled. So the platform
        refused the access correctly and then reported the refusal as a **500**.

        That is the wrong shape for a control that is working:

        * a 500 reads as a platform bug, so a real refusal gets triaged as an
          outage and the finding is lost among genuine errors;
        * every blocked attempt pages whoever watches error monitoring, which is
          how alerting on a security signal gets muted;
        * under DEBUG the error page renders a traceback of the guard itself;
        * and a caller probing for cross-tenant access learns that this endpoint
          behaves differently from the ones that answer a flat 403.

        Nothing about the isolation changes here -- the query was already
        refused before this runs. Only the answer changes, from a crash to a
        denial the caller, the logs and the tests can all read.
        """
        if not isinstance(exception, SecurityIsolationException):
            return None
        logger.warning(
            "tenant boundary violation refused: code=%s detail=%s path=%s",
            getattr(exception, "code", "tenant_boundary_violation"),
            getattr(exception, "detail", "")[:200],
            getattr(request, "path", "")[:200],
        )
        # The message can name the pinned school and the offending value, so it
        # is logged and never returned.
        payload = {
            "error": "tenant_boundary_violation",
            "detail": "Cross-tenant access is not permitted.",
        }
        accept = (request.META.get("HTTP_ACCEPT") or "").lower()
        wants_json = "application/json" in accept or (
            getattr(request, "path", "") or ""
        ).startswith("/api/")
        if wants_json:
            return JsonResponse(payload, status=403)
        return HttpResponseForbidden(payload["detail"])
