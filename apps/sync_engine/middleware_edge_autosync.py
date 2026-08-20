"""Kick the in-process edge sync scheduler from ordinary page loads.

``maybe_run_due_jobs`` is hung off ``/health/``. Render pings that path; a LAN
box often does not. Without this middleware a box with internet still waits
forever unless Celery beat is running. Same throttle as the health tick — the
request thread never runs the cycle.
"""

from __future__ import annotations

from django.conf import settings


class EdgeAutosyncMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        self._maybe_tick(request)
        return self.get_response(request)

    def _maybe_tick(self, request) -> None:
        if not bool(getattr(settings, "RMC_EDGE_SYNC_ENABLED", False)):
            return
        if getattr(settings, "RUNNING_TESTS", False):
            return
        try:
            from apps.schools.gate_request_kind import is_document_navigation

            if not is_document_navigation(request):
                return
            from apps.platform_runtime.periodic import maybe_run_due_jobs

            maybe_run_due_jobs()
        except Exception:  # noqa: BLE001 — never block a page on the scheduler
            return
