"""
Tenant-facing hub: effective runtime / tenant platform settings resolution (read-only) plus
product links. Django admin remains an escape hatch for edge CRUD.
"""

from __future__ import annotations

from typing import Any

from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.urls import NoReverseMatch, reverse
from django.views.decorators.http import require_http_methods

from apps.accounts.decorators import permission_required
from apps.platform_runtime.helpers import get_effective_site_settings

_SAFE_EFFECTIVE_ATTRS = (
    "site_name",
    "school_code",
    "tagline",
    "maintenance_mode",
)


def _truthy_feature_keys(flags: Any) -> list[str]:
    if not isinstance(flags, dict):
        return []
    return sorted(k for k, v in flags.items() if v is True)


@login_required
@permission_required("settings.manage")
@require_http_methods(["GET"])
def tenant_runtime_configuration_hub(request: HttpRequest) -> HttpResponse:
    school = getattr(request, "school", None)
    site = get_effective_site_settings(request=request)

    effective_rows: list[tuple[str, Any]] = []
    if site is not None:
        for attr in _SAFE_EFFECTIVE_ATTRS:
            try:
                val = getattr(site, attr)
            except Exception:
                val = None
            effective_rows.append((attr, val))

    region_rows: list[tuple[str, Any]] = []
    region = getattr(school, "default_region", None) if school else None
    if region is not None:
        region_rows = [
            ("region", getattr(region, "name", None)),
            ("timezone", getattr(region, "timezone", None)),
            ("currency", getattr(region, "default_currency", None)),
        ]

    flags_on: list[str] = []
    if site is not None:
        flags_on = _truthy_feature_keys(getattr(site, "backend_feature_flags", None))

    admin_sitesettings_url = None
    if getattr(request.user, "is_staff", False):
        try:
            admin_sitesettings_url = reverse("admin:siteconfig_sitesettings_changelist")
        except NoReverseMatch:
            admin_sitesettings_url = None

    ctx = {
        "school": school,
        "effective_rows": effective_rows,
        "region_rows": region_rows,
        "flags_on": flags_on,
        "console_url": reverse("siteconfig:console_domains_hub"),
        "feature_control_url": reverse("siteconfig:feature_control_panel"),
        "theme_colors_url": reverse("siteconfig:theme_colors"),
        "school_theme_url": reverse("siteconfig:school_theme_settings"),
        "user_preferences_url": reverse("siteconfig:user_preferences"),
        "admin_sitesettings_url": admin_sitesettings_url,
    }
    return render(request, "siteconfig/tenant_runtime_configuration_hub.html", ctx)
