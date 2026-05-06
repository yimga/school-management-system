from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from django.shortcuts import redirect, render

from apps.accounts.permissions import tenant_operator_hub_eligible
from apps.platform_runtime.administration_catalog import (
    BLUEPRINTS,
    TENANT_CONFIGURATION_SECTIONS,
    enriched_modules,
    module_by_key,
    resolved_pack_rows,
    resolved_registry_rows,
)
from apps.schools.control_plane import require_control_plane_access


@require_control_plane_access
def configuration_center(request):
    return render(
        request,
        "platform_runtime/configuration_center.html",
        {
            "modules": enriched_modules(),
            "page_marker": "rmc-platform-configuration-center",
            "os_center_key": "platform_configuration_center",
            "center_purpose": "Governed facade over existing SiteConfig, Studio OS, marketplace, metadata, runtime, security, billing, and automation systems.",
        },
    )


@require_control_plane_access
def configuration_module_detail(request, module_key: str):
    module = module_by_key(module_key)
    if module is None:
        return HttpResponseForbidden("Unknown platform configuration module.")
    context = {
        "module": module,
        "page_marker": f"rmc-configuration-module-{module_key}",
        "os_center_key": "platform_configuration_center",
        "center_purpose": module["purpose"],
    }
    if module_key == "blueprints":
        context["blueprints"] = BLUEPRINTS
    elif module_key in {"packages", "workflow-packs", "dashboard-packs", "policy-bundles"}:
        context["packs"] = resolved_pack_rows(module_key)
        context["pack_key"] = module_key
    elif module_key == "registries":
        context["registries"] = resolved_registry_rows()
    else:
        context["related_modules"] = enriched_modules()
    return render(request, "platform_runtime/configuration_module_detail.html", context)


def tenant_configuration_forbidden(request, *args, **kwargs):
    return HttpResponseForbidden("Platform configuration requires control-plane access.")


def internal_admin_alias_redirect(request, remaining: str = ""):
    target = "/admin/"
    if remaining:
        target = f"{target}{remaining}"
    if request.GET:
        target = f"{target}?{request.GET.urlencode()}"
    return redirect(target)


@login_required
def school_configuration_center(request):
    school = getattr(request, "school", None)
    if school is None or not tenant_operator_hub_eligible(request.user):
        return HttpResponseForbidden("Tenant school configuration access required.")
    return render(
        request,
        "platform_runtime/school_configuration_center.html",
        {
            "school": school,
            "sections": TENANT_CONFIGURATION_SECTIONS,
            "page_marker": "rmc-school-configuration-center",
        },
    )
