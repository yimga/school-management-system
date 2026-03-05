"""
Workflow engine API: catalog, list tenant workflows, run workflow (first-class Trigger/Condition/Action).
Dashboard registry API: formal tenant-scoped widget list and metadata.
"""
import json
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods

from .workflow_registry import get_workflow_catalog
from .dashboard_registry import get_tenant_dashboard_registry
from .models_workflow import TenantWorkflow
from .workflow_engine import run_workflow


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
def dashboard_registry_api(request):
    """Formal dashboard registry: tenant-scoped widgets + metadata + permissions (built-in + marketplace)."""
    school = getattr(request, "school", None)
    role = (request.GET.get("role") or getattr(request.user, "role", None) or "").strip() or None
    page = (request.GET.get("page") or "").strip() or None
    data = get_tenant_dashboard_registry(school, role=role, page=page)
    return JsonResponse(data)
