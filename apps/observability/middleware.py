"""
Observability middleware: Prometheus metrics + request_id/tenant_id for structured logging (A4).
"""

import logging
import uuid
from time import perf_counter
from prometheus_client import Counter, Histogram
from django.utils.deprecation import MiddlewareMixin

from apps.observability.logging_context import (
    set_request_logging_context,
    set_impersonation_logging_context,
    clear_request_logging_context,
)

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
    """Attach request_id, tenant_id, user_id, school_id to request and logging context (A4)."""

    def process_request(self, request):
        request_id = request.META.get("HTTP_X_REQUEST_ID") or str(uuid.uuid4())
        request.request_id = request_id
        tenant_id = ""
        if hasattr(request, "tenant_ctx") and request.tenant_ctx:
            tenant_id = str(
                getattr(request.tenant_ctx, "tenant_id", "")
                or getattr(request.tenant_ctx, "school_id", "")
                or ""
            )
        request.tenant_id = tenant_id
        user_id = ""
        if (
            getattr(request, "user", None)
            and getattr(request.user, "pk", None)
            and request.user.is_authenticated
        ):
            user_id = str(request.user.pk)
        request.user_id = user_id
        # Wave C #4 Phase 2: operator-impersonation marker. request.user is the
        # operator (not swapped); request.session["impersonation"] carries the
        # impersonated tenant. Surface it for the compliance audit signal.
        during_impersonation = False
        impersonated_school_id = ""
        try:
            session = getattr(request, "session", None)
            imp = session.get("impersonation") if session is not None else None
            if isinstance(imp, dict) and imp.get("school_id"):
                during_impersonation = True
                impersonated_school_id = str(imp.get("school_id") or "")
        except Exception:  # noqa: BLE001 — logging context must never break the request
            during_impersonation = False
            impersonated_school_id = ""
        set_impersonation_logging_context(during_impersonation, impersonated_school_id)
        school_id = ""
        school = getattr(request, "school", None)
        if school is not None and getattr(school, "pk", None) is not None:
            school_id = str(school.pk)
        else:
            ctx = getattr(request, "tenant_ctx", None)
            if ctx is not None:
                raw_sid = getattr(ctx, "school_id", None)
                if raw_sid is not None:
                    school_id = str(raw_sid)
        request.logging_school_id = school_id
        raw_path = getattr(request, "path", None) or ""
        raw_ip = (request.META.get("REMOTE_ADDR") or "").strip()
        if len(raw_ip) > 45:
            raw_ip = raw_ip[:44] + "…"
        raw_referer = (request.META.get("HTTP_REFERER") or "").strip()
        raw_ua = (request.META.get("HTTP_USER_AGENT") or "").strip()
        raw_ct = (getattr(request, "content_type", None) or "").strip()
        try:
            raw_host = (request.get_host() or "").strip()
        except Exception:
            raw_host = (request.META.get("HTTP_HOST") or "").strip()
        raw_al = (request.META.get("HTTP_ACCEPT_LANGUAGE") or "").strip()
        raw_ae = (request.META.get("HTTP_ACCEPT_ENCODING") or "").strip()
        raw_xff = (request.META.get("HTTP_X_FORWARDED_FOR") or "").strip()
        raw_xfp = (request.META.get("HTTP_X_FORWARDED_PROTO") or "").strip()
        raw_xfh = (request.META.get("HTTP_X_FORWARDED_HOST") or "").strip()
        raw_cl = (request.META.get("CONTENT_LENGTH") or "").strip()
        raw_origin = (request.META.get("HTTP_ORIGIN") or "").strip()
        raw_query_string = (request.META.get("QUERY_STRING") or "").strip()
        raw_server_protocol = (request.META.get("SERVER_PROTOCOL") or "").strip()
        raw_request_scheme = (getattr(request, "scheme", None) or "").strip()
        raw_server_name = (request.META.get("SERVER_NAME") or "").strip()
        set_request_logging_context(
            request_id=request_id,
            tenant_id=tenant_id,
            user_id=user_id,
            school_id=school_id,
            http_method=(request.method or "GET").upper(),
            request_path=raw_path,
            remote_addr=raw_ip,
            http_referer=raw_referer,
            http_user_agent=raw_ua,
            http_host=raw_host,
            content_type=raw_ct,
            accept_language=raw_al,
            accept_encoding=raw_ae,
            x_forwarded_for=raw_xff,
            x_forwarded_proto=raw_xfp,
            x_forwarded_host=raw_xfh,
            content_length=raw_cl,
            http_origin=raw_origin,
            query_string=raw_query_string,
            server_protocol=raw_server_protocol,
            request_scheme=raw_request_scheme,
            server_name=raw_server_name,
        )

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

            REQUEST_COUNTER.labels(
                method=method, endpoint=endpoint, status=status
            ).inc()

            started = getattr(request, "_obs_started_at", None)
            elapsed = None
            if started is not None:
                elapsed = perf_counter() - started
                REQUEST_LATENCY.labels(
                    method=method, endpoint=endpoint, status=status
                ).observe(elapsed)

            from apps.observability.slo_metrics import record_web_availability

            record_web_availability(status_code=status, duration_seconds=elapsed)
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
