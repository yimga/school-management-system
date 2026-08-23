"""Orchestration OPERATOR routes (workbench + retry).

The JSON API lives in ``urls_api.py``; a host that wants both includes both.
Every view here is gated by ``require_super_access_with_host``, which refuses
any surface that is neither the manager host nor a ``/super/`` path -- so these
are mounted on the manager host, and deliberately not on a tenant's.
"""

from django.urls import path

from . import views

app_name = "orchestration"

urlpatterns = [
    path("workbench/", views.operator_workbench, name="operator_workbench"),
    path("runs/<int:run_id>/retry/", views.retry_run, name="retry_run"),
]
