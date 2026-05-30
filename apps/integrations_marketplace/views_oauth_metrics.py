"""v4.00.82 — Parallel Prometheus scrape endpoint for LMS OAuth metrics.

WIRING DECISION (also documented in
``apps.integrations_marketplace.lms_oauth_metrics``):

The existing platform Prometheus scrape view
(``apps.observability.views_metrics.PrometheusMetricsView``) calls
``prometheus_client.generate_latest()`` against the library's default
registry. Registering our process-singleton dicts into that registry
from a separate module is fragile — registry state leaks across
test runs and worker reloads, and the prometheus_client API doesn't
make it cheap to unregister between resets.

Rather than refactor the existing /metrics/ view (risky, touches the
v3.39.0 / v3.40.0 Bearer-auth surface), v4.00.82 parks the LMS OAuth
metrics on a parallel endpoint at ``/lms-oauth-metrics/``. Operators
add a second Prometheus scrape job pointing at this URL. The two
endpoints stay independent so a regression in our exporter cannot
break the platform's main metrics surface.

No auth is applied here — the endpoint exposes only cumulative
provider-level counters (no PII, no tenant slugs). Operators MUST
firewall this endpoint at the infra layer (same posture as
``/metrics/`` when its Bearer token is unset) until a richer auth
story lands.
"""
from __future__ import annotations

from django.http import HttpRequest, HttpResponse
from django.views.decorators.http import require_http_methods

from apps.integrations_marketplace.lms_oauth_metrics import (
    render_prometheus_metrics,
)

# Prometheus text-exposition content type per spec.
_PROM_CONTENT_TYPE = "text/plain; version=0.0.4; charset=utf-8"


@require_http_methods(["GET", "HEAD"])
def lms_oauth_metrics_text(request: HttpRequest) -> HttpResponse:
    """GET ``/lms-oauth-metrics/`` — Prometheus text exposition.

    Never raises. ``render_prometheus_metrics`` itself is fail-safe and
    returns an error-marker series rather than blowing up on a bad
    snapshot, so this view's response shape is stable.
    """
    body = render_prometheus_metrics()
    return HttpResponse(body, content_type=_PROM_CONTENT_TYPE)
