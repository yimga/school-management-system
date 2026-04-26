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
from apps.platform_runtime.site_settings_read_access import get_effective_site_settings

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

    try:
        scheduled_hub_url = reverse("siteconfig:scheduled_reports_delivery_hub")
    except NoReverseMatch:
        scheduled_hub_url = None
    try:
        sync_center_url = reverse("siteconfig:sync_center")
    except NoReverseMatch:
        sync_center_url = None
    try:
        report_output_history_evidence_url = reverse(
            "siteconfig:report_output_history_evidence"
        )
    except NoReverseMatch:
        report_output_history_evidence_url = None
    try:
        metadata_operator_hub_url = reverse("siteconfig:metadata_operator_hub")
    except NoReverseMatch:
        metadata_operator_hub_url = None
    try:
        billing_plan_readonly_url = reverse("siteconfig:billing_plan_readonly")
    except NoReverseMatch:
        billing_plan_readonly_url = None

    ctx = {
        "school": school,
        "effective_rows": effective_rows,
        "region_rows": region_rows,
        "flags_on": flags_on,
        "summary_effective_n": len(effective_rows),
        "summary_region_n": len(region_rows),
        "summary_flags_n": len(flags_on),
        "console_url": reverse("siteconfig:console_domains_hub"),
        "feature_control_url": reverse("siteconfig:feature_control_panel"),
        "theme_colors_url": reverse("siteconfig:theme_colors"),
        "school_theme_url": reverse("siteconfig:school_theme_settings"),
        "user_preferences_url": reverse("siteconfig:user_preferences"),
        "scheduled_hub_url": scheduled_hub_url,
        "sync_center_url": sync_center_url,
        "report_output_history_evidence_url": report_output_history_evidence_url,
        "metadata_operator_hub_url": metadata_operator_hub_url,
        "billing_plan_readonly_url": billing_plan_readonly_url,
        "admin_sitesettings_url": admin_sitesettings_url,
    }
    return render(request, "siteconfig/tenant_runtime_configuration_hub.html", ctx)
