"""
Observability middleware: Prometheus metrics + request_id/tenant_id for structured logging (A4).
"""

import logging
import uuid
from time import perf_counter
from prometheus_client import Counter, Histogram
from django.utils.deprecation import MiddlewareMixin

from apps.observability.logging_context import set_request_logging_context, clear_request_logging_context

logger = logging.getLogger(__name__)

REQUEST_COUNTER = Counter(
    "sms_http_requests_total",
    "Total HTTP requests",
    ["method", "endpoint", "status"],
)

REQUEST_LATENCY = Histogram(
    "sms_http_request_latency_seconds",
    "HTTP request latency in seconds",
    ["method", "endpoint", "status"],
    buckets=(0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 4.0, float("inf")),
)


class RequestIdLoggingMiddleware(MiddlewareMixin):
    """Attach request_id, tenant_id, user_id to request and to logging context (A4)."""

    def process_request(self, request):
        request_id = request.META.get("HTTP_X_REQUEST_ID") or str(uuid.uuid4())
        request.request_id = request_id
        tenant_id = ""
        if hasattr(request, "tenant_ctx") and request.tenant_ctx:
            tenant_id = str(getattr(request.tenant_ctx, "tenant_id", "") or getattr(request.tenant_ctx, "school_id", "") or "")
        request.tenant_id = tenant_id
        user_id = ""
        if getattr(request, "user", None) and getattr(request.user, "pk", None) and request.user.is_authenticated:
            user_id = str(request.user.pk)
        request.user_id = user_id
        set_request_logging_context(request_id=request_id, tenant_id=tenant_id, user_id=user_id)

    def process_response(self, request, response):
        clear_request_logging_context()
        if getattr(request, "request_id", None):
            response["X-Request-ID"] = request.request_id
        return response


class ObservabilityMiddleware(MiddlewareMixin):
    """Record basic request metrics for Prometheus."""

    def process_request(self, request):
        request._obs_started_at = perf_counter()

    def process_response(self, request, response):
        try:
            method = (request.method or "GET").upper()
            endpoint = self._resolve_endpoint(request)
            status = getattr(response, "status_code", 500)

            REQUEST_COUNTER.labels(method=method, endpoint=endpoint, status=status).inc()

            started = getattr(request, "_obs_started_at", None)
            if started is not None:
                elapsed = perf_counter() - started
                REQUEST_LATENCY.labels(method=method, endpoint=endpoint, status=status).observe(elapsed)
        except (AttributeError, TypeError, ValueError) as exc:
            logger.debug("Observability metrics record skipped: %s", exc)
        return response

    def _resolve_endpoint(self, request):
        match = getattr(request, "resolver_match", None)
        if match and match.view_name:
            return match.view_name
        # Fallback to path prefix to avoid high cardinality
        path = (request.path or "/").split("?")[0]
        return path.rstrip("/") or "/"
