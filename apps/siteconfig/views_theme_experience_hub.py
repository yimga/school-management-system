"""Theme & Experience hub — tenant school and manager operator entry points."""

from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from django.shortcuts import render
from django.utils.translation import gettext_lazy as _

from apps.schools.control_plane import is_control_plane_request, user_has_control_plane_access
from apps.siteconfig.theme_experience_surfaces import (
    build_platform_theme_experience_surfaces,
    build_tenant_theme_experience_surfaces,
    resolve_operator_school_impersonation_url,
)


@login_required
def theme_experience_hub(request):
    """
    Dual-plane hub: lists every theme/experience surface for the active host.

    Tenants configure their school; manager operators configure platform chrome and
    global defaults without using tenant-primary workflow hubs on the manager host.
    """
    user = request.user
    if is_control_plane_request(request):
        if not user_has_control_plane_access(user):
            return HttpResponseForbidden("Control plane access required.")
    elif not (
        getattr(user, "is_superuser", False)
        or user.has_feature_permission("settings.manage")
    ):
        return HttpResponseForbidden("settings.manage required.")
    operator_plane = is_control_plane_request(request)
    impersonation_url = ""
    if operator_plane:
        surfaces = build_platform_theme_experience_surfaces()
        title = _("Platform theme & experience")
        subtitle = _(
            "Configure RunMyCampus Manager chrome, platform defaults, Studio Experience, "
            "and global branding. Changes here do not replace a single school's tenant branding "
            "— use impersonation on the tenant host for per-school work."
        )
        template_name = "siteconfig/theme_experience_hub_control_plane.html"
        impersonation_url = resolve_operator_school_impersonation_url()
    else:
        surfaces = build_tenant_theme_experience_surfaces()
        title = _("School theme & experience")
        subtitle = _(
            "Configure how this school looks and feels: portals, staff dashboards, theme packs, "
            "and Studio Experience. Your choices apply to this tenant only."
        )
        template_name = "siteconfig/theme_experience_hub_tenant.html"

    return render(
        request,
        template_name,
        {
            "surfaces": surfaces,
            "hub_title": title,
            "hub_subtitle": subtitle,
            "operator_plane": operator_plane,
            "impersonation_url": impersonation_url,
            "page_marker": "rmc-theme-experience-hub",
        },
    )
