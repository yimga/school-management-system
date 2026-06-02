"""
HTTP request envelope for long / mutating operator + tenant API calls.

Starts a WorkflowRun at the beginning of authenticated write requests on
API-like paths; finalizes when the response is sent. Short static/health
paths are excluded.
"""

from __future__ import annotations

import logging
import re
import time
from typing import Callable

logger = logging.getLogger(__name__)

_WRITE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})

_PATH_DENY_RE = re.compile(
    r"(?i)(^/health/|/health/|^/static/|^/media/|workflow-progress|/stream/|"
    r"/badge/|/weather/|csrf|login|logout|session|metrics/?$|"
    r"csrf-token|/rum/|tour-steps|heartbeat|notifications|activities|"
    r"theme.preference|command-bar)"
)

# Views that already use @track_workflow with richer step trains.
_HTTP_EXPLICIT_PATH_SUBSTRINGS = (
    "offboarding/run-scheduled",
    "api/create-school",
    "api/schools/create",
)

# DRF/CBV migration actions enqueue Celery with step-tracked tasks.
_HTTP_EXPLICIT_MIGRATION_ACTION_RE = re.compile(
    r"(?i)/migration/api/v\d+/bundles/\d+/(advance|apply)(/|$)"
)

# Prefixes that should always show progress for operators + tenants.
_PATH_ALLOW_PREFIXES = (
    "/super/api/",
    "/super/migration/",
    "/api/v1/",
    "/api/v2/",
    "/api/migration/",
    "/api/oneroster/",
    "/api/dashboard/",
    "/api/wizards/",
    "/portal/api/",
    "/assist-dock/",
    "/api/",  # tenant + manager REST (health/csrf/etc. denied above)
    "/t/",  # tenant-scoped APIs under path routing
)


def _client_requests_workflow_track(request) -> bool:
    raw = (
        request.headers.get("X-RMC-Workflow-Track")
        if hasattr(request, "headers")
        else None
    ) or request.META.get("HTTP_X_RMC_WORKFLOW_TRACK", "")
    return str(raw).strip() == "1"


def _should_track_request(request) -> bool:
    if request.method not in _WRITE_METHODS:
        return False
    path = getattr(request, "path", "") or ""
    if _PATH_DENY_RE.search(path):
        return False
    if any(fragment in path for fragment in _HTTP_EXPLICIT_PATH_SUBSTRINGS):
        return False
    if _HTTP_EXPLICIT_MIGRATION_ACTION_RE.search(path):
        return False
    user = getattr(request, "user", None)
    if user is None or not getattr(user, "is_authenticated", False):
        return False
    if _client_requests_workflow_track(request):
        return True
    if any(path.startswith(prefix) for prefix in _PATH_ALLOW_PREFIXES):
        return True
    return False


def _workflow_key_for_request(request) -> str:
    try:
        from apps.platform_runtime.workflow_guidance import resolve_workflow_for_route

        workflow = resolve_workflow_for_route(request)
        if workflow is not None and getattr(workflow, "key", ""):
            return str(workflow.key)[:80]
    except Exception:
        logger.debug("workflow_key_registry_resolve_failed", exc_info=True)
    path = (getattr(request, "path", "") or "").strip("/").replace("/", "_")
    return f"http.{request.method.lower()}.{path}"[:80]


class WorkflowProgressRequestMiddleware:
    """Attach a best-effort WorkflowRun to qualifying HTTP writes."""

    def __init__(self, get_response: Callable):
        self.get_response = get_response

    def __call__(self, request):
        run = None
        started = 0.0
        if _should_track_request(request):
            started = time.monotonic()
            try:
                from apps.platform_runtime.workflow_tracker import begin_run

                tenant_schema = ""
                tenant = getattr(request, "tenant", None)
                if tenant is not None:
                    tenant_schema = str(getattr(tenant, "schema_name", "") or "")
                school_id = ""
                school = getattr(request, "school", None)
                if school is not None and getattr(school, "id", None):
                    school_id = str(school.id)
                user = getattr(request, "user", None)
                actor_id = str(getattr(user, "id", "") or "") if user else ""
                run = begin_run(
                    workflow_key=_workflow_key_for_request(request),
                    steps=("request", "response"),
                    request=request,
                    tenant_schema=tenant_schema,
                    school_id=school_id,
                    actor_user_id=actor_id,
                    expected_duration_seconds=90,
                    payload={"path": (request.path or "")[:200], "method": request.method},
                )
                if run is not None:
                    setattr(request, "_rmc_workflow_run", run)
                    from apps.platform_runtime.workflow_tracker import push_workflow_run

                    push_workflow_run(run)
            except Exception:
                logger.debug("workflow_request_middleware_begin_failed", exc_info=True)

        response = None
        view_error: BaseException | None = None
        try:
            response = self.get_response(request)
        except BaseException as exc:
            view_error = exc
            raise
        finally:
            if run is not None:
                try:
                    from apps.platform_runtime.workflow_tracker import (
                        finalize_run,
                        pop_workflow_run,
                        pulse_workflow_step,
                    )

                    elapsed = int(max(0, time.monotonic() - started))
                    if view_error is not None:
                        finalize_run(run, status="failed", error=view_error)
                    else:
                        pulse_workflow_step(
                            run,
                            "response",
                            payload={
                                "status_code": getattr(response, "status_code", 0),
                                "elapsed_ms": elapsed * 1000,
                            },
                        )
                        status = "succeeded"
                        code = int(getattr(response, "status_code", 200) or 200)
                        if code >= 500:
                            status = "failed"
                        finalize_run(
                            run,
                            status=status,
                            error=None if status == "succeeded" else Exception(f"HTTP {code}"),
                        )
                    pop_workflow_run(run)
                except Exception:
                    logger.debug("workflow_request_middleware_finalize_failed", exc_info=True)

        return response
