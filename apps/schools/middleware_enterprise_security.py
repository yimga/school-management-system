"""
Optional enterprise audit for control-plane HTTP mutations (super).

Enable with environment variable ``ENTERPRISE_SUPER_HTTP_AUDIT=1`` (or ``true``).
Complements per-view ``log_control_plane_action``; may produce duplicate lines for
routes that also self-audit — use log analysis to dedupe, or keep disabled.
"""

from __future__ import annotations

import logging

from django.conf import settings
from django.http import HttpRequest

logger = logging.getLogger(__name__)

_UNSAFE = frozenset({"POST", "PUT", "PATCH", "DELETE"})


class EnterpriseSuperHttpAuditMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request: HttpRequest):
        response = self.get_response(request)
        if not getattr(settings, "ENTERPRISE_SUPER_HTTP_AUDIT", False):
            return response
        if request.method not in _UNSAFE:
            return response
        path = request.path or ""
        if not path.startswith("/super/"):
            return response
        # Skip obvious asset paths
        if "/static/" in path or path.endswith(".ico"):
            return response
        if not getattr(request, "user", None) or not request.user.is_authenticated:
            return response
        try:
            from apps.schools.control_plane import (
                log_control_plane_action,
                user_has_control_plane_access,
            )

            if not user_has_control_plane_access(request.user):
                return response
            if response.status_code >= 400:
                return response
            log_control_plane_action(
                request,
                action="UPDATE",
                model_name="SuperHttpMutation",
                object_id=path[:200],
                object_repr=f"{request.method} {path[:180]}",
                reason="enterprise_super_http_audit",
                new_values={
                    "method": request.method,
                    "status_code": response.status_code,
                },
            )
        except Exception as e:
            logger.warning("EnterpriseSuperHttpAuditMiddleware: %s", e)
        return response
