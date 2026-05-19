"""Zero-Ticket Hub — tenant self-service diagnostics, permission simulator, brand guard API."""

from __future__ import annotations

import json

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import render
from django.urls import NoReverseMatch, reverse
from django.views.decorators.http import require_GET, require_http_methods

from apps.accounts.decorators import permission_required
from apps.siteconfig.contrast_guard import remediate_brand_hex_on_background
from apps.siteconfig.permission_matrix_simulator import (
    compare_roles_capabilities,
    export_simulation_csv,
    export_simulation_json,
    list_simulator_roles,
    simulate_role_capabilities,
)
from apps.siteconfig.tenant_diagnostics import run_tenant_diagnostics


@login_required
@permission_required("settings.manage")
@require_GET
def zero_ticket_hub(request):
    """Tenant Health & Diagnostic Canvas — primary self-service entry."""
    diagnostics = run_tenant_diagnostics(request)
    return render(
        request,
        "siteconfig/zero_ticket_hub.html",
        {
            "diagnostics": diagnostics,
            "hub_sections": [
                {
                    "title": "Permission matrix",
                    "description": "Simulate what a role can see before changing live access.",
                    "url_name": "siteconfig:permission_matrix_simulator",
                },
                {
                    "title": "Tenant health",
                    "description": "Score history, risk alerts, and intervention suggestions.",
                    "url_name": "siteconfig:tenant_health_dashboard",
                },
                {
                    "title": "Theme & experience",
                    "description": "Brand colors, contrast guard, and dual-plane theme hub.",
                    "url_name": "siteconfig:theme_experience_hub",
                },
                {
                    "title": "Campus hierarchy",
                    "description": "Parent/child schools and group intelligence.",
                    "url_name": "siteconfig:school_group_hierarchy",
                },
                {
                    "title": "Campus workflow canvas",
                    "description": "Visual automation designer for cross-campus processes.",
                    "url_name": "siteconfig:campus_workflow_canvas_hub",
                },
            ],
        },
    )


@login_required
@permission_required("settings.manage")
@require_GET
def campus_workflow_canvas_hub(request):
    """Salesforce-scale workflow entry — delegates to automation visual designer."""
    designer_url = ""
    gallery_url = ""
    workflow_list_url = ""
    simulate_api = ""
    publish_api = ""
    try:
        designer_url = reverse("automation:visual_workflow_designer")
    except NoReverseMatch:
        designer_url = ""
    try:
        gallery_url = reverse("siteconfig:workflow_flow_gallery")
    except NoReverseMatch:
        gallery_url = ""
    try:
        workflow_list_url = reverse("automation:visual_workflow_list")
    except NoReverseMatch:
        workflow_list_url = ""
    try:
        simulate_api = reverse("automation:visual_workflow_simulate")
    except NoReverseMatch:
        simulate_api = ""
    try:
        publish_api = reverse("automation:visual_workflow_publish")
    except NoReverseMatch:
        publish_api = ""
    return render(
        request,
        "siteconfig/campus_workflow_canvas_hub.html",
        {
            "designer_url": designer_url,
            "gallery_url": gallery_url,
            "workflow_list_url": workflow_list_url,
            "simulate_api": simulate_api,
            "publish_api": publish_api,
        },
    )


@login_required
@permission_required("settings.manage")
@require_GET
def permission_matrix_simulator(request):
    school = getattr(request, "school", None)
    role = (request.GET.get("role") or "TEACHER").strip().upper()
    roles = list_simulator_roles()
    simulation = simulate_role_capabilities(school=school, role=role)
    return render(
        request,
        "siteconfig/permission_matrix_simulator.html",
        {
            "roles": roles,
            "selected_role": role,
            "simulation": simulation,
        },
    )


@login_required
@permission_required("settings.manage")
@require_http_methods(["POST"])
def api_permission_matrix_simulate(request):
    try:
        payload = json.loads(request.body.decode("utf-8") or "{}")
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({"error": "invalid_json"}, status=400)
    role = (payload.get("role") or "").strip().upper()
    if not role:
        return JsonResponse({"error": "role_required"}, status=400)
    school = getattr(request, "school", None)
    return JsonResponse(simulate_role_capabilities(school=school, role=role))


@login_required
@permission_required("settings.manage")
@require_http_methods(["GET", "POST"])
def api_permission_matrix_export(request):
    """Export simulated capabilities as JSON or CSV; POST supports role comparison."""
    school = getattr(request, "school", None)
    if request.method == "POST":
        try:
            payload = json.loads(request.body.decode("utf-8") or "{}")
        except (json.JSONDecodeError, UnicodeDecodeError):
            return JsonResponse({"error": "invalid_json"}, status=400)
        roles = payload.get("roles") or []
        if not isinstance(roles, list) or not roles:
            role = (payload.get("role") or "TEACHER").strip().upper()
            roles = [role]
        fmt = (payload.get("format") or "json").strip().lower()
        if len(roles) > 1:
            body = compare_roles_capabilities(
                school=school, roles=[str(r).upper() for r in roles]
            )
            if fmt == "csv":
                lines = ["capability,label," + ",".join(roles)]
                for row in body["comparison"]:
                    vis = ",".join(
                        "yes" if row["roles"].get(r) else "no" for r in roles
                    )
                    lines.append(f"{row['key']},{row['label']},{vis}")
                return JsonResponse(
                    {"csv": "\n".join(lines), "format": "csv"},
                )
            return JsonResponse(body)
        simulation = simulate_role_capabilities(
            school=school, role=str(roles[0]).upper()
        )
        if fmt == "csv":
            return JsonResponse(
                {"csv": export_simulation_csv(simulation), "format": "csv"}
            )
        return JsonResponse(export_simulation_json(simulation))

    role = (request.GET.get("role") or "TEACHER").strip().upper()
    fmt = (request.GET.get("format") or "json").strip().lower()
    simulation = simulate_role_capabilities(school=school, role=role)
    if fmt == "csv":
        from django.http import HttpResponse

        resp = HttpResponse(export_simulation_csv(simulation), content_type="text/csv")
        resp["Content-Disposition"] = (
            f'attachment; filename="permission-matrix-{role.lower()}.csv"'
        )
        return resp
    return JsonResponse(export_simulation_json(simulation))


@login_required
@permission_required("settings.manage")
@require_http_methods(["POST"])
def api_brand_contrast_remediate(request):
    """Intercept inaccessible brand picks; return hue-shifted compliant hex."""
    try:
        payload = json.loads(request.body.decode("utf-8") or "{}")
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({"error": "invalid_json"}, status=400)
    brand = (payload.get("brand_hex") or payload.get("primary_color") or "").strip()
    background = (
        payload.get("background_hex") or payload.get("surface_hex") or "#ffffff"
    ).strip()
    min_ratio = float(payload.get("min_ratio") or 7.0)
    result = remediate_brand_hex_on_background(
        brand, background, min_ratio=min_ratio
    )
    return JsonResponse(result)


@login_required
@permission_required("settings.manage")
@require_GET
def api_tenant_diagnostics(request):
    return JsonResponse(run_tenant_diagnostics(request))
