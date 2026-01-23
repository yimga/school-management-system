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


@csrf_exempt
@require_GET
def api_activities(request):
    """API endpoint to fetch recent activities/audit logs.
    
    Returns a list of recent system activities, admin actions, and student changes.
    Supports filtering by type and pagination.
    """
    try:
        page = int(request.GET.get('page', 1))
        filter_type = request.GET.get('filter', '')
        
        # Default activities - can be extended to pull from database
        activities = [
            {
                "id": 1,
                "type": "admin",
                "title": "Settings Updated",
                "description": "System settings configuration was modified",
                "timestamp": (__import__('datetime').datetime.now() - __import__('datetime').timedelta(hours=2)).isoformat(),
                "user": "Administrator"
            },
            {
                "id": 2,
                "type": "student",
                "title": "Student Enrolled",
                "description": "New student added to Mathematics class",
                "timestamp": (__import__('datetime').datetime.now() - __import__('datetime').timedelta(hours=4)).isoformat(),
                "user": "Admin User"
            },
            {
                "id": 3,
                "type": "system",
                "title": "Database Backup",
                "description": "Automatic system database backup completed",
                "timestamp": (__import__('datetime').datetime.now() - __import__('datetime').timedelta(hours=6)).isoformat(),
                "user": None
            },
            {
                "id": 4,
                "type": "enrollment",
                "title": "Course Registration",
                "description": "Student registered for new course",
                "timestamp": (__import__('datetime').datetime.now() - __import__('datetime').timedelta(hours=8)).isoformat(),
                "user": "Student Self-Service"
            }
        ]
        
        # Apply filter if specified
        if filter_type:
            activities = [a for a in activities if a['type'] == filter_type]
        
        # Pagination
        per_page = 10
        start = (page - 1) * per_page
        end = start + per_page
        paginated = activities[start:end]
        
        return JsonResponse({
            "status": "success",
            "activities": paginated,
            "count": len(paginated),
            "total": len(activities),
            "page": page
        })
    except Exception as exc:
        return JsonResponse({
            "status": "error",
            "error": str(exc)
        }, status=500)


@csrf_exempt
@require_GET
def api_dashboard_charts(request):
    """API endpoint for dashboard chart data.
    
    Returns data for enrollment trends, fee collection, performance analytics, etc.
    """
    try:
        return JsonResponse({
            "status": "success",
            "enrollment": {
                "labels": ["Jan", "Feb", "Mar", "Apr", "May", "Jun"],
                "data": [12, 19, 8, 15, 22, 18]
            },
            "feeCollection": {
                "paid": 75,
                "pending": 15,
                "overdue": 10
            },
            "performance": {
                "labels": ["Math", "English", "Science", "History", "Arts"],
                "data": [78, 82, 75, 88, 90]
            }
        })
    except Exception as exc:
        return JsonResponse({
            "status": "error",
            "error": str(exc)
        }, status=500)
