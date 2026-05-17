"""
Platform operators on tenant host: canonical manager-host shell for siteconfig routes.
"""

from __future__ import annotations

from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect
from django.urls import resolve, Resolver404

from apps.schools.control_plane import (
    is_control_plane_request,
    user_has_control_plane_access,
)
from apps.schools.tenant_url import build_manager_absolute_url
from apps.siteconfig.staff_navigation import is_manager_control_plane

# Platform-operator siteconfig routes that must use manager chrome (not tenant portal).
_MANAGER_CANONICAL_VIEW_NAMES = frozenset(
    {
        "siteconfig:ai_center",
        "siteconfig:ai_governance",
        "siteconfig:console_domains_hub",
        "siteconfig:feature_control_panel",
        "siteconfig:feature_control_audit",
        "siteconfig:feature_control_ledger",
        "siteconfig:guided_configuration_workflows",
        "siteconfig:theme_colors",
        "siteconfig:dashboard_hub",
        "siteconfig:dashboard_configuration_hub",
        "siteconfig:reportcard_builder",
        "siteconfig:scheduled_reports_delivery_hub",
        "siteconfig:tenant_runtime_configuration_hub",
        "siteconfig:metadata_operator_hub",
        "siteconfig:onboarding",
        "siteconfig:tag_manager",
        "siteconfig:billing_plan_readonly",
        "siteconfig:legacy_customizer",
        "siteconfig:region_validation",
        "siteconfig:region_comparison",
        "siteconfig:region_grading_scales",
        "siteconfig:maintenance",
    }
)


def _should_redirect_operator_to_manager(request: HttpRequest) -> bool:
    if is_manager_control_plane(request) or is_control_plane_request(request):
        return False
    user = getattr(request, "user", None)
    if not user or not getattr(user, "is_authenticated", False):
        return False
    return user_has_control_plane_access(user)


class OperatorSiteconfigManagerShellMiddleware:
    """
    SUPERADMIN / superuser bookmarks to tenant-host siteconfig operator URLs
    are redirected to the same path on the manager host (control-plane shell).
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        if _should_redirect_operator_to_manager(request):
            try:
                match = resolve(request.path_info)
            except Resolver404:
                return self.get_response(request)
            view_name = match.view_name or ""
            if view_name in _MANAGER_CANONICAL_VIEW_NAMES:
                target = build_manager_absolute_url(request, request.get_full_path())
                return redirect(target)
        return self.get_response(request)
