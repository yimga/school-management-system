"""
No-code school automation: visual builder + JSON APIs (simulate, publish, run).
"""

import json

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import redirect
from apps.siteconfig.control_plane_render import (
    default_operator_breadcrumbs,
    operator_cp_breadcrumb,
    render_siteconfig_stem,
)
from django.utils.translation import gettext as _

from django.urls import reverse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods

from .models_workflow import SchoolAutomationWorkflow, SchoolWorkflowExecutionLog
from .workflow_engine import (
    get_school_workflow_dsl,
    retry_failed_actions_from_log,
    run_school_workflow,
    simulate_dsl,
    validate_school_workflow_dsl,
)


def _school_staff_api(request):
    if not getattr(request.user, "is_staff", False):
        return None, JsonResponse({"error": "forbidden"}, status=403)
    school = getattr(request, "school", None)
    if not school:
        return None, JsonResponse({"error": "No school context"}, status=400)
    return school, None


@never_cache
@login_required
@require_http_methods(["GET"])
def school_automation_builder(request):
    if not getattr(request.user, "is_staff", False):
        messages.warning(request, "Access restricted to staff.")
        return redirect(reverse("accounts:backend_dashboard"))
    school = getattr(request, "school", None)
    if not school:
        messages.warning(request, "No school context.")
        return redirect(reverse("accounts:backend_dashboard"))

    SchoolAutomationWorkflow.objects.filter(school=school).order_by("-updated_at")
    try:
        reverse("siteconfig:workflow_flow_gallery")
    except Exception:
        reverse("accounts:backend_dashboard")
    return render_siteconfig_stem(
        request,
        "school_automation_builder",
        None,
        cp_title=_("School automation builder"),
        breadcrumbs=default_operator_breadcrumbs(
            operator_cp_breadcrumb(_("School automation builder"), active=True),
        ),
    )


@require_http_methods(["GET"])
@login_required
def school_automation_list_api(request):
    school, err = _school_staff_api(request)
    if err:
        return err
    out = []
    for wf in SchoolAutomationWorkflow.objects.filter(school=school).order_by("name"):
        out.append(
            {
                "id": wf.id,
                "name": wf.name,
                "trigger": wf.trigger,
                "status": wf.status,
                "is_active": wf.is_active,
                "updated_at": wf.updated_at.isoformat() if wf.updated_at else None,
            }
        )
    return JsonResponse({"workflows": out})


@require_http_methods(["POST"])
@login_required
def school_automation_save_api(request):
    school, err = _school_staff_api(request)
    if err:
        return err
    try:
        body = json.loads(request.body) if request.body else {}
    except json.JSONDecodeError:
        return JsonResponse({"ok": False, "error": "Invalid JSON"}, status=400)

    name = (body.get("name") or "").strip() or "Untitled workflow"
    trigger = (body.get("trigger") or "").strip()
    if not trigger:
        return JsonResponse({"ok": False, "error": "trigger is required"}, status=400)

    wid = body.get("id")
    if wid:
        try:
            wf = SchoolAutomationWorkflow.objects.get(id=int(wid), school=school)
        except (ValueError, SchoolAutomationWorkflow.DoesNotExist):
            return JsonResponse({"ok": False, "error": "Workflow not found"}, status=404)
    else:
        wf = SchoolAutomationWorkflow(school=school)

    wf.name = name[:160]
    wf.trigger = trigger[:80]
    wf.trigger_config = body.get("trigger_config") or {}
    wf.conditions = body.get("conditions") or []
    wf.actions = body.get("actions") or []
    wf.graph = body.get("graph") or {}
    st = body.get("status")
    if st in ("draft", "published", "archived"):
        wf.status = st
    if "is_active" in body:
        wf.is_active = bool(body["is_active"])
    wf.save()
    return JsonResponse(
        {
            "ok": True,
            "id": wf.id,
            "status": wf.status,
            "validation_errors": validate_school_workflow_dsl(get_school_workflow_dsl(wf)),
        }
    )


@require_http_methods(["POST"])
@login_required
def school_automation_publish_api(request):
    school, err = _school_staff_api(request)
    if err:
        return err
    try:
        body = json.loads(request.body) if request.body else {}
    except json.JSONDecodeError:
        return JsonResponse({"ok": False, "error": "Invalid JSON"}, status=400)

    wid = body.get("id")
    if not wid:
        return JsonResponse({"ok": False, "error": "id required"}, status=400)
    try:
        wf = SchoolAutomationWorkflow.objects.get(id=int(wid), school=school)
    except (ValueError, SchoolAutomationWorkflow.DoesNotExist):
        return JsonResponse({"ok": False, "error": "Workflow not found"}, status=404)

    dsl = get_school_workflow_dsl(wf)
    errs = validate_school_workflow_dsl(dsl)
    if errs:
        return JsonResponse({"ok": False, "validation_errors": errs}, status=400)
    wf.status = SchoolAutomationWorkflow.Status.PUBLISHED
    wf.save(update_fields=["status", "updated_at"])
    return JsonResponse({"ok": True, "id": wf.id, "status": wf.status})


@require_http_methods(["POST"])
@login_required
def school_automation_simulate_api(request):
    school, err = _school_staff_api(request)
    if err:
        return err
    try:
        body = json.loads(request.body) if request.body else {}
    except json.JSONDecodeError:
        return JsonResponse({"ok": False, "error": "Invalid JSON"}, status=400)

    context = body.get("context")
    if not isinstance(context, dict):
        context = {}

    dsl = body.get("dsl")
    if isinstance(dsl, dict):
        sim = simulate_dsl(dsl, context, school=school, user=request.user)
        return JsonResponse({"ok": True, **sim})

    wid = body.get("id")
    if not wid:
        return JsonResponse({"ok": False, "error": "dsl or id required"}, status=400)
    try:
        wf = SchoolAutomationWorkflow.objects.get(id=int(wid), school=school)
    except (ValueError, SchoolAutomationWorkflow.DoesNotExist):
        return JsonResponse({"ok": False, "error": "Workflow not found"}, status=404)

    sim = simulate_dsl(get_school_workflow_dsl(wf), context, school=school, user=request.user)
    return JsonResponse({"ok": True, **sim})


@require_http_methods(["POST"])
@login_required
def school_automation_run_api(request):
    school, err = _school_staff_api(request)
    if err:
        return err
    try:
        body = json.loads(request.body) if request.body else {}
    except json.JSONDecodeError:
        return JsonResponse({"ok": False, "error": "Invalid JSON"}, status=400)

    wid = body.get("id")
    if not wid:
        return JsonResponse({"ok": False, "error": "id required"}, status=400)
    try:
        wf = SchoolAutomationWorkflow.objects.get(id=int(wid), school=school)
    except (ValueError, SchoolAutomationWorkflow.DoesNotExist):
        return JsonResponse({"ok": False, "error": "Workflow not found"}, status=404)

    context = body.get("context")
    if not isinstance(context, dict):
        context = {}

    use_async = bool(body.get("async"))
    if use_async:
        from .tasks import execute_school_workflow_async

        async_result = execute_school_workflow_async.delay(
            int(wid), context, user_id=getattr(request.user, "id", None)
        )
        return JsonResponse(
            {
                "ok": True,
                "queued": True,
                "task_id": async_result.id,
            }
        )

    result = run_school_workflow(wf, context, user=request.user)
    return JsonResponse({"ok": True, **result})


@require_http_methods(["GET"])
@login_required
def school_automation_execution_logs_api(request):
    """Recent execution logs for the tenant (optional workflow_id filter)."""
    school, err = _school_staff_api(request)
    if err:
        return err
    wf_id = request.GET.get("workflow_id")
    qs = SchoolWorkflowExecutionLog.objects.filter(workflow__school=school).select_related(
        "workflow"
    )
    if wf_id:
        try:
            qs = qs.filter(workflow_id=int(wf_id))
        except ValueError:
            return JsonResponse({"error": "invalid workflow_id"}, status=400)
    rows = []
    logs = list(qs.order_by("-created_at")[:80])
    latest_failed = set()
    seen_wf = set()
    for lg in logs:
        if lg.workflow_id in seen_wf:
            continue
        seen_wf.add(lg.workflow_id)
        if lg.run_status == SchoolWorkflowExecutionLog.RunStatus.FAILED:
            latest_failed.add(lg.id)
    for lg in logs:
        rows.append(
            {
                "id": lg.id,
                "workflow_id": lg.workflow_id,
                "workflow_name": lg.workflow.name,
                "conditions_passed": lg.conditions_passed,
                "run_status": lg.run_status,
                "retry_count": lg.retry_count,
                "created_at": lg.created_at.isoformat() if lg.created_at else None,
                "has_action_errors": any(
                    isinstance(r, dict) and r.get("error") for r in (lg.actions_run or [])
                ),
                "needs_attention": lg.id in latest_failed,
            }
        )
    return JsonResponse({"logs": rows})


@require_http_methods(["POST"])
@login_required
def school_automation_retry_api(request):
    """Retry failed actions for one execution log (uses stored context_snapshot)."""
    school, err = _school_staff_api(request)
    if err:
        return err
    try:
        body = json.loads(request.body) if request.body else {}
    except json.JSONDecodeError:
        return JsonResponse({"ok": False, "error": "Invalid JSON"}, status=400)

    log_id = body.get("execution_log_id")
    if log_id is None:
        return JsonResponse({"ok": False, "error": "execution_log_id required"}, status=400)
    try:
        log = SchoolWorkflowExecutionLog.objects.select_related("workflow").get(
            pk=int(log_id), workflow__school=school
        )
    except (ValueError, SchoolWorkflowExecutionLog.DoesNotExist):
        return JsonResponse({"ok": False, "error": "Execution log not found"}, status=404)

    ctx_over = body.get("context")
    if ctx_over is not None and not isinstance(ctx_over, dict):
        return JsonResponse({"ok": False, "error": "context must be an object"}, status=400)

    use_async = bool(body.get("async"))
    if use_async:
        from .tasks import retry_school_workflow_execution_async

        ar = retry_school_workflow_execution_async.delay(
            int(log.pk),
            context_override=ctx_over or {},
            user_id=getattr(request.user, "id", None),
        )
        return JsonResponse({"ok": True, "queued": True, "task_id": ar.id})

    result = retry_failed_actions_from_log(
        log.pk,
        user=request.user,
        context_override=ctx_over or {},
    )
    return JsonResponse({"ok": True, **result})
