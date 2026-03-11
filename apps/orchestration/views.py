"""
Orchestration operator workbench (Phase 10 — 4.1 stub).
Long-running process list, status, retry, compensation. Full UI in future sprints.
"""
from django.contrib.admin.views.decorators import staff_member_required
from django.db.utils import ProgrammingError
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from .models import OrchestrationRun


@staff_member_required
def operator_workbench(request):
    """Operator view: list recent orchestration runs, SLA overdue, retries (4.1)."""
    runs = []
    runs_overdue = []
    try:
        qs = OrchestrationRun.objects.select_related("definition", "school").order_by("-created_at")[:100]
        runs = list(qs)
        runs_overdue = [r for r in runs if getattr(r, "sla_overdue", False)]
    except ProgrammingError:
        # Table not created yet (migrations not applied) — show empty workbench until migrate runs
        pass
    return render(
        request,
        "orchestration/operator_workbench.html",
        {"runs": runs, "runs_overdue": runs_overdue},
    )


@staff_member_required
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
