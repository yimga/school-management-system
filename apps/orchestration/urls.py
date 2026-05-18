from django.urls import path
from . import views, api

app_name = "orchestration"
urlpatterns = [
    path("workbench/", views.operator_workbench, name="operator_workbench"),
    path("runs/<int:run_id>/retry/", views.retry_run, name="retry_run"),
    # Move 2: public JSON API.
    path("api/runs/", api.runs_list_or_create, name="api_runs_list_or_create"),
    path("api/runs/<int:run_id>/", api.run_detail, name="api_run_detail"),
    path("api/runs/<int:run_id>/events/", api.run_events, name="api_run_events"),
    path("api/runs/<int:run_id>/cancel/", api.run_cancel, name="api_run_cancel"),
    path("api/runs/<int:run_id>/retry/", api.run_retry, name="api_run_retry"),
    path("api/slo/", api.slo_snapshot, name="api_slo_snapshot"),
]
