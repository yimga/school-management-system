# -*- coding: utf-8 -*-
"""Middleware-enforced dual-dashboard topology separation."""

from __future__ import annotations

from django.http import HttpResponseForbidden, JsonResponse
from django.shortcuts import render
from django.utils.translation import gettext as _

from apps.schools.dashboard_rbac import (
    evaluate_dashboard_topology_access,
    log_topology_violation,
)


class DashboardTopologyRBACMiddleware:
    """
    Reject cross-tier dashboard access with a helpful permission page.

    Runs after AuthenticationMiddleware. Complements ModuleAccessMiddleware and
    ManagerHostControlPlaneRequiredMiddleware.
    """

    SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.process_request(request)
        if response is not None:
            return response
        return self.get_response(request)

    def process_request(self, request):
        decision = evaluate_dashboard_topology_access(request)
        if decision.allowed:
            return None

        log_topology_violation(request, decision)

        path = getattr(request, "path", "") or ""
        if path.startswith("/api/"):
            return JsonResponse(
                {
                    "detail": _(
                        "This action belongs to the configuration dashboard. "
                        "Your role can use the operational dashboard only."
                    ),
                    "dashboard_tier": decision.tier,
                    "reason": decision.reason,
                    "redirect_hint": decision.redirect_hint,
                },
                status=403,
            )

        accept = (request.headers.get("Accept") or "").lower()
        if "text/html" in accept or "*/*" in accept:
            return render(
                request,
                "errors/dashboard_topology_denied.html",
                {
                    "tier": decision.tier,
                    "reason": decision.reason,
                    "redirect_hint": decision.redirect_hint,
                    "operational_label": _("Operational dashboard"),
                    "config_label": _("Configuration dashboard"),
                },
                status=403,
            )

        return HttpResponseForbidden(
            "Dashboard topology access denied for this role."
        )
