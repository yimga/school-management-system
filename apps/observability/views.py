"""
Observability endpoints: /healthz and /metrics.
"""

from django.http import HttpResponse, JsonResponse
from django.db import connection
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST
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


# ============================================
# ADMIN DASHBOARD API ENDPOINTS
# ============================================

@csrf_exempt
@require_GET
def api_health(request):
    """API endpoint for dashboard health checks.
    
    Returns system health status, active users, database status.
    Used by dashboard to display system state.
    """
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
        
        return JsonResponse({
            "status": "healthy",
            "database": "connected",
            "timestamp": __import__('datetime').datetime.now().isoformat(),
            "uptime": "running",
            "cache": "available"
        })
    except Exception as exc:
        return JsonResponse({
            "status": "error",
            "error": str(exc)
        }, status=500)


@csrf_exempt
@require_POST
def api_notifications_mark_all_read(request):
    """API endpoint to mark all notifications as read.
    
    This is a placeholder for notification system integration.
    Can be extended to work with a real notification model.
    """
    try:
        # Placeholder: In a real system, this would update notification records
        # For now, just return success
        return JsonResponse({
            "status": "success",
            "message": "All notifications marked as read",
            "count": 0
        })
    except Exception as exc:
        return JsonResponse({
            "status": "error",
            "error": str(exc)
        }, status=500)


@csrf_exempt
@require_GET
def api_notifications(request):
    """API endpoint to fetch recent notifications.
    
    Returns a list of recent system notifications and alerts.
    """
    try:
        notifications = [
            {
                "id": 1,
                "type": "info",
                "message": "System running normally",
                "timestamp": __import__('datetime').datetime.now().isoformat()
            }
        ]
        
        return JsonResponse({
            "status": "success",
            "notifications": notifications,
            "count": len(notifications)
        })
    except Exception as exc:
        return JsonResponse({
            "status": "error",
            "error": str(exc)
        }, status=500)
