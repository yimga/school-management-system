"""Automation app URLs. Step 41: outcomes console (bounded console for outcomes, not raw settings)."""

from django.urls import path

from . import views
from . import views_visual_workflow
from . import views_workflow_gallery

app_name = "automation"

urlpatterns = [
    path("outcomes/", views.outcomes_console, name="outcomes_console"),
    path(
        "workflow-template-gallery/",
        views_workflow_gallery.workflow_template_gallery,
        name="workflow_template_gallery",
    ),
    path(
        "workflow-template-gallery/<slug:template_id>/dry-run/",
        views_workflow_gallery.workflow_template_dry_run,
        name="workflow_template_dry_run",
    ),
    path(
        "workflows/designer/",
        views_visual_workflow.visual_workflow_designer,
        name="visual_workflow_designer",
    ),
    path(
        "workflows/api/list/",
        views_visual_workflow.visual_workflow_list,
        name="visual_workflow_list",
    ),
    path(
        "workflows/api/save-graph/",
        views_visual_workflow.visual_workflow_save_graph,
        name="visual_workflow_save_graph",
    ),
    path(
        "workflows/api/simulate/",
        views_visual_workflow.visual_workflow_simulate,
        name="visual_workflow_simulate",
    ),
    path(
        "workflows/api/dispatch-test/",
        views_visual_workflow.visual_workflow_dispatch_test,
        name="visual_workflow_dispatch_test",
    ),
    path(
        "workflows/api/validate-graph/",
        views_visual_workflow.visual_workflow_validate_graph,
        name="visual_workflow_validate_graph",
    ),
    path(
        "workflows/api/publish/",
        views_visual_workflow.visual_workflow_publish,
        name="visual_workflow_publish",
    ),
    path(
        "workflows/api/rollback/",
        views_visual_workflow.visual_workflow_rollback,
        name="visual_workflow_rollback",
    ),
]
