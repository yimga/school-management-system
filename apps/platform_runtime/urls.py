from django.urls import path

from apps.platform_runtime.views_operational_center import (
    implementation_command_center,
    implementation_missing_data_blockers_json,
    pilot_defect_dashboard,
    pilot_evidence_dashboard,
    support_playbook_center,
)
from apps.platform_runtime.views_tenant_lifecycle import tenant_lifecycle_dashboard
from apps.platform_runtime.views_workflow_progress import (
    active_runs_view as workflow_progress_active_runs_view,
    apply_fix_view as workflow_progress_apply_fix_view,
    badge_view as workflow_progress_badge_view,
    cancel_view as workflow_progress_cancel_view,
    run_detail_view as workflow_progress_run_detail_view,
    stream_view as workflow_progress_stream_view,
)
from apps.platform_runtime.views_newsletter import (
    newsletter_confirm_view,
    newsletter_subscribe_view,
    newsletter_unsubscribe_view,
)

urlpatterns = [
    path(
        "lifecycle/",
        tenant_lifecycle_dashboard,
        name="tenant_lifecycle_dashboard",
    ),
    path(
        "implementation/",
        implementation_command_center,
        name="implementation_command_center",
    ),
    path(
        "implementation/blockers.json",
        implementation_missing_data_blockers_json,
        name="implementation_missing_data_blockers_json",
    ),
    path(
        "support-playbooks/",
        support_playbook_center,
        name="support_playbook_center",
    ),
    path(
        "pilot-evidence/",
        pilot_evidence_dashboard,
        name="pilot_evidence_dashboard",
    ),
    path(
        "pilot-defects/",
        pilot_defect_dashboard,
        name="pilot_defect_dashboard",
    ),
    # Workflow Progress Bus — platform-wide (v4.00.96).
    path(
        "workflow-progress/active/",
        workflow_progress_active_runs_view,
        name="workflow_progress_active_runs",
    ),
    path(
        "workflow-progress/badge/",
        workflow_progress_badge_view,
        name="workflow_progress_badge",
    ),
    path(
        "workflow-progress/stream/",
        workflow_progress_stream_view,
        name="workflow_progress_stream",
    ),
    path(
        "workflow-progress/detail/<int:run_id>/",
        workflow_progress_run_detail_view,
        name="workflow_progress_run_detail",
    ),
    path(
        "workflow-progress/cancel/<int:run_id>/",
        workflow_progress_cancel_view,
        name="workflow_progress_cancel",
    ),
    path(
        "workflow-progress/apply-fix/<int:run_id>/",
        workflow_progress_apply_fix_view,
        name="workflow_progress_apply_fix",
    ),
    # Newsletter subscription (v4.00.98 Phase 3).
    path(
        "newsletter/subscribe/",
        newsletter_subscribe_view,
        name="newsletter_subscribe",
    ),
    path(
        "newsletter/confirm/<str:token>/",
        newsletter_confirm_view,
        name="newsletter_confirm",
    ),
    path(
        "newsletter/unsubscribe/<str:token>/",
        newsletter_unsubscribe_view,
        name="newsletter_unsubscribe",
    ),
]
