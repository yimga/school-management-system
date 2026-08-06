"""
Orchestration Workflow Center (operator).

Browse process definitions, launch runs, and inspect each run's step-event
timeline. Sits on top of the existing orchestration engine (models + JSON API +
Celery runners) — this is its operator UI. Retry/compensation live here too.
"""

import logging

from django.contrib import messages
from django.db.utils import ProgrammingError
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from apps.platform_runtime.models import PlatformOperatorOrchestrationWorkbenchLink
from apps.schools.control_plane import require_super_access_with_host

from . import event_log, versioning
from .models import (
    OrchestrationRun,
    OrchestrationStepEvent,
    ProcessDefinition,
)

logger = logging.getLogger(__name__)


@require_super_access_with_host
def operator_workbench(request):
    """Operator view: list recent orchestration runs, SLA overdue, retries (4.1)."""
    runs = []
    runs_overdue = []
    try:
        qs = OrchestrationRun.objects.select_related("definition", "school").order_by(
            "-created_at"
        )[:100]
        runs = list(qs)
        runs_overdue = [r for r in runs if getattr(r, "sla_overdue", False)]
    except ProgrammingError:
        # Table not created yet (migrations not applied) — show empty workbench until migrate runs
        pass
    operator_orchestration_workbench_links = list(
        PlatformOperatorOrchestrationWorkbenchLink.objects.order_by("sort_order", "slug")
    )
    # Browsable process-definition catalogue — the operator can see what workflows
    # exist and launch one, instead of only being able to watch runs others started.
    definitions = []
    try:
        for defn in ProcessDefinition.objects.order_by("name", "code")[:100]:
            definitions.append(
                {
                    "code": defn.code,
                    "name": defn.name or defn.code,
                    "description": defn.description,
                    "current_version": defn.current_version,
                    "run_count": OrchestrationRun.objects.filter(definition=defn).count(),  # tenant-isolation-allow: operator-workbench-platform-scope-staff-required
                }
            )
    except ProgrammingError:
        pass
    return render(
        request,
        "orchestration/operator_workbench.html",
        {
            "runs": runs,
            "runs_overdue": runs_overdue,
            "definitions": definitions,
            "operator_orchestration_workbench_links": operator_orchestration_workbench_links,
        },
    )


@require_super_access_with_host
@require_POST
def start_run(request, code):
    """Launch a run of a process definition from the Workflow Center.

    Mirrors the JSON API's create path (create PENDING run → bind current version
    → emit RUN_CREATED) so both entry points behave identically. Version-bind and
    event-emit are best-effort: a run is still recorded if either bookkeeping step
    fails, and the failure is logged rather than 500-ing the operator.
    """
    defn = get_object_or_404(ProcessDefinition, code=code)
    run = OrchestrationRun.objects.create(
        definition=defn,
        school=getattr(request, "school", None),
        status=OrchestrationRun.Status.PENDING,
        input_payload={},
        triggered_by=request.user if request.user.is_authenticated else None,
    )
    try:
        versioning.bind_run_to_current_version(run)
    except Exception:  # noqa: BLE001 — bookkeeping must not fail the launch
        logger.warning(
            "orchestration.start_run: version bind failed for run %s", run.pk,
            exc_info=True,
        )
    try:
        event_log.emit(
            run,
            event_type=OrchestrationStepEvent.EventType.RUN_CREATED,
            payload={"by": request.user.pk, "via": "workbench"},
        )
    except Exception:  # noqa: BLE001 — event log must not fail the launch
        logger.warning(
            "orchestration.start_run: event emit failed for run %s", run.pk,
            exc_info=True,
        )
    messages.success(
        request,
        _("Started run #%(id)s for %(name)s.")
        % {"id": run.pk, "name": defn.name or defn.code},
    )
    return redirect(reverse("super:orchestration_run_detail", args=[run.pk]))


@require_super_access_with_host
def run_detail_page(request, run_id: int):
    """Operator run detail: status + the full step-event timeline for one run."""
    run = get_object_or_404(
        OrchestrationRun.objects.select_related(
            "definition", "definition_version", "school"
        ),
        pk=run_id,
    )
    events = list(
        OrchestrationStepEvent.objects.filter(run=run).order_by(
            "sequence_number", "created_at"
        )[:500]
    )
    return render(
        request,
        "orchestration/run_detail.html",
        {"run": run, "events": events},
    )


@require_super_access_with_host
def retry_run(request, run_id: int):
    """Re-queue a failed run (set status to PENDING, clear completed_at). Phase 10 — 4.1."""
    run = get_object_or_404(OrchestrationRun, pk=run_id)
    if run.status != OrchestrationRun.Status.FAILED:
        return redirect(reverse("super:orchestration_workbench"))
    run.status = OrchestrationRun.Status.PENDING
    run.completed_at = None
    run.error_message = ""
    run.save(update_fields=["status", "completed_at", "error_message", "updated_at"])
    return redirect(reverse("super:orchestration_workbench"))
