"""Prometheus HTTP scrape exporter (v3.39.0 Agent 4; v3.40.0 Bearer auth).

Exposed at ``/metrics/`` ONLY when
``settings.OBSERVABILITY_METRICS_BACKEND == "prometheus-client"``;
the URL wiring in ``config/urls.py`` is lazy and skipped on every
other backend.

**v3.40.0 — opt-in Bearer-token auth.** When
``settings.OBSERVABILITY_METRICS_BEARER_TOKEN`` is set (non-empty string)
the endpoint REQUIRES ``Authorization: Bearer <token>`` and uses
``hmac.compare_digest`` for constant-time compare. A miss returns 401
with ``WWW-Authenticate: Bearer realm="observability"`` so well-behaved
Prometheus scrape configs surface the auth requirement clearly.

When the env var is unset (``None``) the legacy anonymous mode is
preserved — this is a deliberate backward-compat path so operators can
flip the env var when ready WITHOUT a coordinated deploy. In production
operators MUST set either the bearer token OR firewall the endpoint at
the infra layer (network ACL on the Prometheus scrape subnet, or a
sidecar nginx with allow-list). The rbac-allow marker below documents
that boundary so the role-permission audit doesn't flag missing auth.

Tenant-specific labels arriving here are already
sha256[:12]-hashed by v3.38.0 Agent 4's ``_hash_tenant_id`` —
plaintext tenant slugs never appear in metric series, so the
endpoint is safe to expose to operations team even though it
shows every tenant's emission rate.

**Secrets discipline**: the bearer token value is NEVER logged. The 401
response carries only the realm; the request's ``Authorization`` header
is never echoed; ``hmac.compare_digest`` ensures comparison is
constant-time so timing attacks can't probe the token byte by byte.
"""
from __future__ import annotations

import hmac
import importlib

from django.conf import settings
from django.http import HttpResponse, HttpResponseNotFound
from django.views.generic import View


class PrometheusMetricsView(View):
    """GET ``/metrics/`` — returns the Prometheus exposition format.

    Returns 404 when the prometheus_client backend isn't active so a
    misconfigured deployment doesn't accidentally expose an empty
    metric registry.

    Returns 401 with ``WWW-Authenticate: Bearer realm="observability"``
    when ``OBSERVABILITY_METRICS_BEARER_TOKEN`` is configured AND the
    request's ``Authorization`` header is absent / malformed / wrong.
    """

    # rbac-allow: prometheus-scrape-bearer-or-firewall-protected
    http_method_names = ["get", "head"]

    def _unauthorized(self) -> HttpResponse:
        resp = HttpResponse(b"Unauthorized", status=401, content_type="text/plain")
        resp["WWW-Authenticate"] = 'Bearer realm="observability"'
        return resp

    def _check_bearer(self, request) -> HttpResponse | None:
        """Return None on success, or an HttpResponse(401) on miss.

        Treats both ``None`` AND empty-string settings as "auth disabled"
        (legacy anonymous mode). Constant-time compare via
        ``hmac.compare_digest`` so timing attacks can't byte-probe.
        """
        expected = getattr(settings, "OBSERVABILITY_METRICS_BEARER_TOKEN", None)
        if not expected:  # None or "" → legacy unauthenticated mode
            return None
        header = request.META.get("HTTP_AUTHORIZATION", "") or ""
        # Parse "Bearer <token>" — be strict; we never log the value.
        if not header.startswith("Bearer "):
            return self._unauthorized()
        presented = header[len("Bearer "):].strip()
        if not presented:
            return self._unauthorized()
        # hmac.compare_digest requires same-length bytes; encode both.
        try:
            ok = hmac.compare_digest(
                presented.encode("utf-8"),
                str(expected).encode("utf-8"),
            )
        except (TypeError, ValueError):
            return self._unauthorized()
        if not ok:
            return self._unauthorized()
        return None

    def get(self, request, *args, **kwargs):
        unauth = self._check_bearer(request)
        if unauth is not None:
            return unauth
        try:
            pc = importlib.import_module("prometheus_client")
        except ImportError:
            return HttpResponseNotFound("prometheus_client not installed")
        try:
            payload = pc.generate_latest()
            content_type = getattr(
                pc, "CONTENT_TYPE_LATEST", "text/plain; version=0.0.4; charset=utf-8",
            )
        except Exception:  # noqa: BLE001 - never blow up on scrape
            return HttpResponseNotFound("prometheus_client.generate_latest failed")
        return HttpResponse(payload, content_type=content_type)
