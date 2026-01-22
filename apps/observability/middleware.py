"""
Observability middleware for Prometheus metrics.
Collects request counts and latency with low-cardinality labels to avoid metric blowup.
"""

from time import perf_counter
from prometheus_client import Counter, Histogram
from django.utils.deprecation import MiddlewareMixin

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
        except Exception:
            # Never break the response flow
            pass
        return response

    def _resolve_endpoint(self, request):
        match = getattr(request, "resolver_match", None)
        if match and match.view_name:
            return match.view_name
        # Fallback to path prefix to avoid high cardinality
        path = (request.path or "/").split("?")[0]
        return path.rstrip("/") or "/"
