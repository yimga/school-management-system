from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render

from apps.accounts.permissions import tenant_operator_hub_eligible
from apps.platform_runtime.administration_catalog import (
    BLUEPRINTS,
    TENANT_CONFIGURATION_SECTIONS,
    enriched_modules,
    module_by_key,
    resolved_pack_rows,
    resolved_registry_rows,
)
from apps.platform_runtime.blueprint_apply import apply_blueprint
from apps.platform_runtime.blueprint_contract import get_blueprint, list_blueprints
from apps.platform_runtime.blueprint_impact import analyze_blueprint_impact
from apps.platform_runtime.blueprint_preview import preview_blueprint
from apps.platform_runtime.blueprint_rollback import rollback_blueprint_installation
from apps.platform_runtime.models import BlueprintInstallation
from apps.schools.control_plane import require_control_plane_access
from apps.schools.models import School


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


def _selected_school(request):
    slug = (request.GET.get("school") or request.POST.get("school") or "").strip()
    if not slug:
        return School.objects.filter(is_active=True).order_by("name").first()
    return School.objects.filter(slug=slug).first()


@require_control_plane_access
def blueprint_marketplace(request):
    schools = School.objects.filter(is_active=True).order_by("name")[:50]
    return render(
        request,
        "platform_runtime/blueprint_marketplace.html",
        {
            "blueprints": list_blueprints(),
            "schools": schools,
            "selected_school": _selected_school(request),
            "page_marker": "rmc-blueprint-marketplace-depth",
        },
    )


@require_control_plane_access
def blueprint_detail(request, key: str):
    blueprint = get_blueprint(key)
    if blueprint is None:
        return HttpResponseForbidden("Unknown blueprint.")
    return render(
        request,
        "platform_runtime/blueprint_detail.html",
        {
            "blueprint": blueprint.as_dict(),
            "selected_school": _selected_school(request),
        },
    )


@require_control_plane_access
def blueprint_preview_view(request, key: str):
    school = _selected_school(request)
    result = preview_blueprint(
        key,
        school=school,
        actor=request.user,
        platform_operator=True,
        emit_audit=True,
    )
    return render(
        request,
        "platform_runtime/blueprint_preview.html",
        {"preview": result, "selected_school": school},
    )


@require_control_plane_access
def blueprint_impact_view(request, key: str):
    school = _selected_school(request)
    result = analyze_blueprint_impact(
        key,
        school=school,
        actor=request.user,
        platform_operator=True,
        emit_audit=True,
    )
    return render(
        request,
        "platform_runtime/blueprint_impact.html",
        {"impact": result, "selected_school": school},
    )


@require_control_plane_access
def blueprint_apply_view(request, key: str):
    school = _selected_school(request)
    preview = preview_blueprint(key, school=school, actor=request.user, platform_operator=True)
    result = None
    if request.method == "POST":
        result = apply_blueprint(
            key,
            school=school,
            actor=request.user,
            preview_snapshot=preview,
            confirmed=request.POST.get("confirm") == "yes",
            platform_operator=True,
        )
        if result.get("ok"):
            return redirect("configuration:blueprint_installation_detail", installation_id=result["installation_id"])
    return render(
        request,
        "platform_runtime/blueprint_apply.html",
        {"preview": preview, "result": result, "selected_school": school},
    )


@require_control_plane_access
def blueprint_installations(request):
    installations = BlueprintInstallation.objects.select_related("school", "applied_by")[:100]
    return render(
        request,
        "platform_runtime/blueprint_installations.html",
        {"installations": installations},
    )


@require_control_plane_access
def blueprint_installation_detail(request, installation_id: int):
    installation = get_object_or_404(
        BlueprintInstallation.objects.select_related("school", "applied_by"),
        pk=installation_id,
    )
    return render(
        request,
        "platform_runtime/blueprint_installation_detail.html",
        {"installation": installation},
    )


@require_control_plane_access
def blueprint_rollback_view(request, installation_id: int):
    installation = get_object_or_404(
        BlueprintInstallation.objects.select_related("school", "applied_by"),
        pk=installation_id,
    )
    result = None
    if request.method == "POST":
        result = rollback_blueprint_installation(
            installation,
            actor=request.user,
            confirmed=request.POST.get("confirm") == "yes",
        )
    return render(
        request,
        "platform_runtime/blueprint_rollback.html",
        {"installation": installation, "result": result},
    )


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


@login_required
def tenant_blueprint_setup(request):
    school = getattr(request, "school", None)
    if school is None or not tenant_operator_hub_eligible(request.user):
        return HttpResponseForbidden("Tenant school configuration access required.")
    blueprints = list_blueprints(tenant_safe_only=True)
    selected_key = (
        request.POST.get("blueprint") or request.GET.get("blueprint") or blueprints[0]["key"]
    ).strip()
    preview = preview_blueprint(
        selected_key,
        school=school,
        actor=request.user,
        platform_operator=False,
        emit_audit=request.GET.get("preview") == "1",
    )
    result = None
    if request.method == "POST":
        result = apply_blueprint(
            selected_key,
            school=school,
            actor=request.user,
            confirmed=request.POST.get("confirm") == "yes",
            platform_operator=False,
        )
    return render(
        request,
        "platform_runtime/tenant_blueprint_setup.html",
        {
            "school": school,
            "blueprints": blueprints,
            "selected_key": selected_key,
            "preview": preview,
            "result": result,
            "page_marker": "rmc-tenant-blueprint-setup",
        },
    )
