"""
Workflow engine API: catalog, list tenant workflows, run workflow (first-class Trigger/Condition/Action).
Dashboard registry API: formal tenant-scoped widget list and metadata.
"""
import json
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods

from .workflow_registry import get_workflow_catalog
from .dashboard_resolver import for_role as dashboard_for_role
from .models_workflow import TenantWorkflow, WorkflowTemplate
from .workflow_engine import run_workflow, get_effective_workflow_dsl


@require_http_methods(["GET"])
@login_required
def workflow_catalog_api(request):
    """Return Trigger / Condition / Action catalog for tenant UI."""
    catalog = get_workflow_catalog()
    return JsonResponse(catalog)


@require_http_methods(["GET"])
@login_required
def workflow_list_api(request):
    """List active workflow assignments for the current school."""
    school = getattr(request, "school", None)
    if not school:
        return JsonResponse({"error": "No school context"}, status=400)
    assignments = TenantWorkflow.objects.filter(school=school, is_active=True).select_related("template")
    out = []
    for a in assignments:
        t = a.template
        out.append({
            "id": a.id,
            "template_code": t.code,
            "template_name": t.name,
            "trigger": t.trigger,
            "overrides": a.overrides or {},
        })
    return JsonResponse({"workflows": out})


@require_http_methods(["POST"])
@login_required
def workflow_run_api(request):
    """Run a tenant workflow by id with optional context. Body: { "tenant_workflow_id": int, "context": dict }."""
    school = getattr(request, "school", None)
    if not school:
        return JsonResponse({"ok": False, "error": "No school context"}, status=400)
    try:
        body = json.loads(request.body) if request.body else {}
    except json.JSONDecodeError:
        return JsonResponse({"ok": False, "error": "Invalid JSON"}, status=400)
    tw_id = body.get("tenant_workflow_id")
    if tw_id is None:
        return JsonResponse({"ok": False, "error": "tenant_workflow_id required"}, status=400)
    try:
        tw = TenantWorkflow.objects.get(id=tw_id, school=school, is_active=True)
    except TenantWorkflow.DoesNotExist:
        return JsonResponse({"ok": False, "error": "Workflow not found or inactive"}, status=404)
    context = body.get("context")
    if not isinstance(context, dict):
        context = {}
    result = run_workflow(tw, context)
    return JsonResponse(result)


@require_http_methods(["GET"])
@login_required
def workflow_preview_api(request):
    """
    Section 5.6: Workflow Hub preview/staging — return effective DSL for a template
    (and optional tenant_workflow_id) without running. For validation and preview.
    """
    school = getattr(request, "school", None)
    if not school:
        return JsonResponse({"error": "No school context"}, status=400)
    template_id = request.GET.get("template_id")
    tw_id = request.GET.get("tenant_workflow_id")
    out = {"effective_dsl": None, "template": None, "staging": bool(request.GET.get("staging"))}
    if tw_id:
        try:
            tw = TenantWorkflow.objects.filter(school=school).select_related("template").get(id=tw_id)
        except (ValueError, TenantWorkflow.DoesNotExist):
            return JsonResponse({"error": "Tenant workflow not found"}, status=404)
        out["effective_dsl"] = get_effective_workflow_dsl(tw)
        out["template"] = {"id": tw.template_id, "code": tw.template.code, "name": tw.template.name}
        out["is_active"] = tw.is_active
        return JsonResponse(out)
    if template_id:
        try:
            t = WorkflowTemplate.objects.get(pk=template_id, is_active=True)
        except (ValueError, WorkflowTemplate.DoesNotExist):
            return JsonResponse({"error": "Template not found"}, status=404)
        tw = TenantWorkflow.objects.filter(school=school, template=t).first()
        if tw:
            out["effective_dsl"] = get_effective_workflow_dsl(tw)
        else:
            out["effective_dsl"] = {
                "trigger": t.trigger,
                "trigger_config": t.trigger_config or {},
                "conditions": t.conditions or [],
                "actions": t.actions or [],
                "overrides": {},
            }
        out["template"] = {"id": t.id, "code": t.code, "name": t.name, "certified": getattr(t, "certified", False)}
        return JsonResponse(out)
    return JsonResponse({"error": "template_id or tenant_workflow_id required"}, status=400)


@require_http_methods(["GET"])
@login_required
def dashboard_registry_api(request):
    """Formal dashboard registry: tenant-scoped widgets + metadata + permissions (built-in + marketplace). Phase 4: use dashboard hub."""
    school = getattr(request, "school", None)
    role = (request.GET.get("role") or getattr(request.user, "role", None) or "").strip() or None
    page = (request.GET.get("page") or "").strip() or None
    runtime = getattr(request, "tenant_runtime", None)
    if runtime is not None and getattr(runtime, "_school", None):
        dash = runtime.dashboard_for(role=role, user=request.user, page=page or "backend", include_registry=True)
    else:
        dash = dashboard_for_role(school, role, user=request.user, page=page or "backend", include_registry=True)
    data = dash.get("registry") or {}
    return JsonResponse(data)
