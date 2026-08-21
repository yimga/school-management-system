"""Kick the in-process periodic scheduler from ordinary page loads.

``maybe_run_due_jobs`` is hung off ``/health/``. Render pings that path; a LAN
box often does not. Without this middleware a box with internet still waits
forever unless Celery beat is running. Same throttle as the health tick — the
request thread never runs the cycle.

WHY THIS FILE EXISTS AT ALL, AND WHY IT WAS NOT WORKING. Until 2026-08-20 this
class was defined here and referenced NOWHERE ELSE in the repository — it was in
no ``MIDDLEWARE`` list and no test. The fallback written for exactly this failure
had never run in production. On the sovereign box that meant four independent
drivers of the periodic tick were dead at once:

  1. ``inprocess_scheduler_enabled()`` stands the in-process scheduler down while
     ``CELERY_BROKER_URL`` is set, and the selfhost compose always sets one;
  2. Celery beat's canary was stale and the broker had no ``celery`` queue at all,
     so beat could not run the schedule it had been handed;
  3. this middleware was never registered;
  4. ``deploy/selfhost/docker-compose.yml`` declared a healthcheck on ``db`` only,
     so nothing pinged ``/health/`` either.

Each layer assumed a different layer owned the schedule. All four are addressed;
this is the one that makes ordinary human use of the box enough to keep it synced.

GATING. The gate is "does this deployment run the in-process scheduler?", not
"is edge sync on?". The narrower flag was wrong twice over: a self-hosted box that
is not an edge box has exactly the same dead-tick problem and loses provisioning
heals and digests with it, and ``RMC_EDGE_SYNC_ENABLED`` lives in a host ``.env``
that nobody editing the pairing screen can see. ``maybe_run_due_jobs`` already
makes the real decision — it is a monotonic comparison in memory, returns
immediately when the scheduler is disabled or under tests, and hands all cache I/O
and job execution to a daemon thread at most once per throttle window per process.
Wiring it globally therefore costs a dict lookup and a float compare on document
navigations, and nothing at all on the cloud, where Render's own probe has already
advanced the window.
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
        if getattr(settings, "RUNNING_TESTS", False):
            return
        try:
            # Ordered cheapest-first: RUNNING_TESTS is a settings lookup, this one can
            # reach the database. It sits INSIDE the try because the whole point of the
            # broad except below is that a page load never dies for the scheduler --
            # an unreachable database here must skip the tick, not 500 the request.
            from apps.sync_engine.edge_enabled import edge_sync_enabled

            if not edge_sync_enabled():
                return
            from apps.schools.gate_request_kind import is_document_navigation

            # Subresources, XHR and fetch are excluded: a single page load already
            # advances the window, and ticking per-asset would only burn the check.
            if not is_document_navigation(request):
                return
            from apps.platform_runtime.periodic import maybe_run_due_jobs

            maybe_run_due_jobs()
        except Exception:  # noqa: BLE001 — never block a page on the scheduler
            return
