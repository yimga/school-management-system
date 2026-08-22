"""Orchestration JSON API routes, split out so a tenant host can mount them.

``urls.py`` holds the OPERATOR surface (workbench + retry), which belongs on the
manager host alone. This module holds the six JSON endpoints described in
``apps/orchestration/api.py``, which are session-or-JWT authenticated and
school-scoped for non-staff callers -- so a school's own subdomain must serve
them.

Both modules were previously one file included only from ``config/urls.py`` --
the urlconf a dev machine or bare-IP host resolves to. Production hosts are
routed by ``UrlConfSwitcherMiddleware`` to tenant/manager/public urlconfs, so
every orchestration route 404'd everywhere except a developer's laptop.

Separate ``app_name`` because a single urlconf mounts BOTH (the manager host
serves the operator UI and the API), and two includes cannot share a namespace.
Paths are unchanged: ``urls.py`` re-exports these under the same ``api/``
prefix it always used, so an existing ``/orchestration/api/...`` URL still
resolves.
"""

from django.urls import path

from . import api

app_name = "orchestration_api"

urlpatterns = [
    path("runs/", api.runs_list_or_create, name="api_runs_list_or_create"),
    path("runs/<int:run_id>/", api.run_detail, name="api_run_detail"),
    path("runs/<int:run_id>/events/", api.run_events, name="api_run_events"),
    path("runs/<int:run_id>/cancel/", api.run_cancel, name="api_run_cancel"),
    path("runs/<int:run_id>/retry/", api.run_retry, name="api_run_retry"),
    path("slo/", api.slo_snapshot, name="api_slo_snapshot"),
]
