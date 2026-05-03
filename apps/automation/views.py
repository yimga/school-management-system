"""
Step 41: Bounded console for automation outcomes (not raw settings).
Surfaces MigrationRun and AutomationExecutionLog results for operators; no profile/playbook editing here.
"""

from django.contrib.auth.decorators import login_required, user_passes_test
from django.db.models import Count, Q
from django.shortcuts import render
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from .models import AutomationExecutionLog, MigrationRun
from .workflow_graph_models import WorkflowRunLog


def _staff_required(user):
    return getattr(user, "is_staff", False) or getattr(user, "is_superuser", False)


@login_required
@user_passes_test(_staff_required)
def outcomes_console(request):
    """
    Outcomes-only console: recent migration runs, execution logs, and visual workflow runs.
    No raw settings (profiles, playbooks); read-only outcome summary.
    """
    school = getattr(request, "school", None)
    base_runs = MigrationRun.objects.all().select_related(
        "triggered_by", "school"
    ).annotate(quarantine_record_count=Count("quarantine_records"))
    base_logs = AutomationExecutionLog.objects.all().select_related(
        "triggered_by", "school"
    )
    if school is not None:
        base_runs = base_runs.filter(Q(school__isnull=True) | Q(school=school))
        base_logs = base_logs.filter(Q(school__isnull=True) | Q(school=school))
    recent_runs = list(base_runs.order_by("-started_at")[:30])
    recent_logs = list(base_logs.order_by("-started_at")[:30])
    recent_visual_runs: list[WorkflowRunLog] = []
    if school is not None:
        recent_visual_runs = list(
            WorkflowRunLog.objects.filter(workflow__school=school)
            .select_related("workflow", "triggered_by")
            .order_by("-created_at")[:30]
        )
    return render(
        request,
        "automation/outcomes_console.html",
        {
            "recent_runs": recent_runs,
            "recent_logs": recent_logs,
            "recent_visual_runs": recent_visual_runs,
            "page_title": _("Automation outcomes"),
            "page_subtitle": _(
                "Recent migration runs, automation execution logs, and visual workflow "
                "run history. Outcomes only; manage profiles and playbooks in Configuration Engine."
            ),
            "action_url": reverse("studio_os:automation"),
            "action_text": _("Back to Automation"),
        },
    )
