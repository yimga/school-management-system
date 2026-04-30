"""Automation app URLs. Step 41: outcomes console (bounded console for outcomes, not raw settings)."""

from django.urls import path

from . import views
from . import views_visual_workflow

app_name = "automation"

urlpatterns = [
    path("outcomes/", views.outcomes_console, name="outcomes_console"),
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
]
