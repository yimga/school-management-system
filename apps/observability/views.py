"""
Observability endpoints: /healthz and /metrics.
"""

from django.http import HttpResponse, JsonResponse
from django.db import connection
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST


@require_GET
def healthz(request):
    """Basic health check including DB connectivity."""
    try:
        # Simple DB round-trip
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
        status = "ok"
    except Exception as exc:  # noqa: BLE001
        return JsonResponse({"status": "error", "error": str(exc)}, status=500)

    return JsonResponse({"status": status})


@csrf_exempt
@require_GET
def metrics(request):
    """Prometheus metrics endpoint."""
    output = generate_latest()
    return HttpResponse(output, content_type=CONTENT_TYPE_LATEST)
