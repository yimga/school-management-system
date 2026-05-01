"""Tenant UI + JSON APIs for relational visual workflows."""

from __future__ import annotations

import json

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods

from apps.automation.graph_compiler import compile_workflow_to_dsl
from apps.automation.graph_validate import validate_workflow_for_publish
from apps.automation.visual_executor import (
    run_matching_visual_workflows,
    simulate_workflow,
)
from apps.automation.workflow_graph_models import Workflow, WorkflowEdge, WorkflowNode


def _staff_school(request):
    if not getattr(request.user, "is_staff", False):
        return None, JsonResponse({"error": "forbidden"}, status=403)
    school = getattr(request, "school", None)
    if not school:
        return None, JsonResponse({"error": "No school context"}, status=400)
    return school, None


@never_cache
@login_required
@require_http_methods(["GET"])
def visual_workflow_designer(request):
    """Studio-linked canvas: palette + save graph (staff, tenant)."""
    if not getattr(request.user, "is_staff", False):
        messages.warning(request, "Staff only.")
        return redirect(reverse("accounts:backend_dashboard"))
    school = getattr(request, "school", None)
    if not school:
        messages.warning(request, "Open from your school domain.")
        return redirect(reverse("accounts:backend_dashboard"))

    workflows = Workflow.objects.filter(school=school).order_by("-updated_at")[:50]
    hub = ""
    try:
        hub = reverse("siteconfig:school_automation_builder")
    except Exception:
        hub = reverse("accounts:backend_dashboard")

    return render(
        request,
        "automation/visual_workflow_designer.html",
        {
            "school": school,
            "workflows": workflows,
            "save_graph_url": reverse("automation:visual_workflow_save_graph"),
            "simulate_url": reverse("automation:visual_workflow_simulate"),
            "publish_url": reverse("automation:visual_workflow_publish"),
            "rollback_url": reverse("automation:visual_workflow_rollback"),
            "list_url": reverse("automation:visual_workflow_list"),
            "school_automation_url": hub,
            "page_title": "Visual workflows",
            "page_subtitle": "Drag nodes, connect edges, publish, then dispatch with domain triggers.",
        },
    )


@require_http_methods(["GET"])
@login_required
def visual_workflow_list(request):
    school, err = _staff_school(request)
    if err:
        return err
    out = []
    for wf in Workflow.objects.filter(school=school).order_by("name"):
        out.append(
            {
                "id": wf.pk,
                "name": wf.name,
                "trigger_event": wf.trigger_event,
                "status": wf.status,
                "is_active": wf.is_active,
                "updated_at": wf.updated_at.isoformat() if wf.updated_at else None,
            }
        )
    return JsonResponse({"workflows": out})


@require_http_methods(["POST"])
@login_required
def visual_workflow_save_graph(request):
    """Persist nodes + edges (replace-all per workflow)."""
    school, err = _staff_school(request)
    if err:
        return err
    try:
        body = json.loads(request.body) if request.body else {}
    except json.JSONDecodeError:
        return JsonResponse({"ok": False, "error": "Invalid JSON"}, status=400)

    wf_id = body.get("workflow_id")
    name = (body.get("name") or "Untitled flow").strip()[:160]
    trigger_event = (body.get("trigger_event") or "").strip()
    nodes_in = body.get("nodes") or []
    edges_in = body.get("edges") or []

    if wf_id:
        wf = Workflow.objects.filter(pk=int(wf_id), school=school).first()
        if not wf:
            return JsonResponse({"ok": False, "error": "workflow not found"}, status=404)
        wf.name = name or wf.name
        if trigger_event:
            wf.trigger_event = trigger_event
        wf.save(update_fields=["name", "trigger_event", "updated_at"])
    else:
        if not trigger_event:
            return JsonResponse(
                {"ok": False, "error": "trigger_event required for new workflow"},
                status=400,
            )
        wf = Workflow.objects.create(
            school=school,
            name=name,
            trigger_event=trigger_event,
            status=Workflow.Status.DRAFT,
        )

    WorkflowEdge.objects.filter(workflow=wf).delete()
    WorkflowNode.objects.filter(workflow=wf).delete()

    ext_to_pk = {}
    for n in nodes_in:
        if not isinstance(n, dict):
            continue
        eid = str(n.get("id") or n.get("external_id") or "").strip()[:64]
        kind = str(n.get("kind") or n.get("type") or "").strip().lower()
        allowed_kinds = {c.value for c in WorkflowNode.Kind}
        if kind not in allowed_kinds:
            continue
        if not eid:
            continue
        node = WorkflowNode.objects.create(
            workflow=wf,
            external_id=eid,
            kind=kind,
            config=n.get("config") if isinstance(n.get("config"), dict) else {},
            position=n.get("position") if isinstance(n.get("position"), dict) else {},
        )
        ext_to_pk[eid] = node.pk

    for e in edges_in:
        if not isinstance(e, dict):
            continue
        src = str(e.get("from") or e.get("source") or "").strip()
        tgt = str(e.get("to") or e.get("target") or "").strip()
        if src not in ext_to_pk or tgt not in ext_to_pk:
            continue
        WorkflowEdge.objects.create(
            workflow=wf,
            source_id=ext_to_pk[src],
            target_id=ext_to_pk[tgt],
            label=str(e.get("label") or "")[:64],
        )

    dsl = compile_workflow_to_dsl(wf)
    return JsonResponse(
        {
            "ok": True,
            "workflow_id": wf.pk,
            "compiled": dsl,
        }
    )


@require_http_methods(["POST"])
@login_required
def visual_workflow_simulate(request):
    school, err = _staff_school(request)
    if err:
        return err
    try:
        body = json.loads(request.body) if request.body else {}
    except json.JSONDecodeError:
        return JsonResponse({"ok": False, "error": "Invalid JSON"}, status=400)
    wf_id = body.get("workflow_id")
    sample = body.get("sample_payload") or {}
    if not wf_id:
        return JsonResponse({"ok": False, "error": "workflow_id required"}, status=400)
    wf = Workflow.objects.filter(pk=int(wf_id), school=school).first()
    if not wf:
        return JsonResponse({"ok": False, "error": "not found"}, status=404)
    prev = simulate_workflow(wf.pk, sample, user=request.user)
    return JsonResponse({"ok": True, **prev})


@require_http_methods(["POST"])
@login_required
def visual_workflow_dispatch_test(request):
    """Dry-run all matching workflows for a trigger (preview integration)."""
    school, err = _staff_school(request)
    if err:
        return err
    try:
        body = json.loads(request.body) if request.body else {}
    except json.JSONDecodeError:
        return JsonResponse({"ok": False, "error": "Invalid JSON"}, status=400)
    trigger_type = (body.get("trigger_type") or "").strip()
    ctx = body.get("context") if isinstance(body.get("context"), dict) else {}
    if not trigger_type:
        return JsonResponse({"ok": False, "error": "trigger_type required"}, status=400)
    rows = run_matching_visual_workflows(
        school, trigger_type, ctx, user=request.user, dry_run=True
    )
    return JsonResponse({"ok": True, "results": rows})


@require_http_methods(["POST"])
@login_required
def visual_workflow_publish(request):
    """Publish workflow after structural validation (invalid graphs return 400)."""
    school, err = _staff_school(request)
    if err:
        return err
    try:
        body = json.loads(request.body) if request.body else {}
    except json.JSONDecodeError:
        return JsonResponse({"ok": False, "error": "Invalid JSON"}, status=400)
    wf_id = body.get("workflow_id")
    if not wf_id:
        return JsonResponse({"ok": False, "error": "workflow_id required"}, status=400)
    wf = Workflow.objects.filter(pk=int(wf_id), school=school).first()
    if not wf:
        return JsonResponse({"ok": False, "error": "not found"}, status=404)
    errs = validate_workflow_for_publish(wf.pk)
    if errs:
        return JsonResponse({"ok": False, "validation_errors": errs}, status=400)
    wf.status = Workflow.Status.PUBLISHED
    wf.save(update_fields=["status", "updated_at"])
    return JsonResponse({"ok": True, "workflow_id": wf.pk, "status": wf.status})


@require_http_methods(["POST"])
@login_required
def visual_workflow_rollback(request):
    """Move workflow back to draft (operator rollback; does not delete nodes)."""
    school, err = _staff_school(request)
    if err:
        return err
    try:
        body = json.loads(request.body) if request.body else {}
    except json.JSONDecodeError:
        return JsonResponse({"ok": False, "error": "Invalid JSON"}, status=400)
    wf_id = body.get("workflow_id")
    if not wf_id:
        return JsonResponse({"ok": False, "error": "workflow_id required"}, status=400)
    wf = Workflow.objects.filter(pk=int(wf_id), school=school).first()
    if not wf:
        return JsonResponse({"ok": False, "error": "not found"}, status=404)
    wf.status = Workflow.Status.DRAFT
    wf.save(update_fields=["status", "updated_at"])
    return JsonResponse({"ok": True, "workflow_id": wf.pk, "status": wf.status})
