"""
Observability endpoints: /healthz and /metrics.
"""

from functools import wraps

from django.conf import settings
from django.http import HttpResponse, JsonResponse, HttpResponseForbidden
from django.db import connection
from django.views.decorators.http import require_GET, require_POST
from django.shortcuts import render
from django.contrib.auth.decorators import login_required, user_passes_test
from django.utils import timezone
from django.db.models import Count, Q, Value
from django.db.models.functions import Coalesce
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
from django.core.cache import cache


def _is_observability_authorized(request) -> bool:
    """Allow staff users or holders of the observability API key."""
    api_key = getattr(settings, "OBSERVABILITY_API_KEY", "")
    if api_key:
        header_key = request.headers.get("X-OBSERVABILITY-KEY") or request.META.get("HTTP_X_OBSERVABILITY_KEY")
        if header_key == api_key:
            return True

    user = getattr(request, "user", None)
    if user and user.is_authenticated:
        return user.is_staff or user.is_superuser or getattr(user, "role", None) == "ADMIN"
    return False


def observability_auth_required(view_func):
    """Require staff session auth; allow API key for safe GET/HEAD requests."""
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if request.method in ("GET", "HEAD"):
            if _is_observability_authorized(request):
                return view_func(request, *args, **kwargs)
        else:
            user = getattr(request, "user", None)
            if user and user.is_authenticated and (user.is_staff or user.is_superuser or getattr(user, "role", None) == "ADMIN"):
                return view_func(request, *args, **kwargs)

        return HttpResponseForbidden("Forbidden")
    return _wrapped


@require_GET
@observability_auth_required
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


@require_GET
@observability_auth_required
def metrics(request):
    """Prometheus metrics endpoint."""
    base_output = generate_latest()

    # Append AI Copilot lightweight counters from cache in Prometheus text format
    lines = []
    try:
        total = cache.get('ai_copilot_usage_total') or 0
        denied = cache.get('ai_copilot_usage_denied_total') or 0
        roles = cache.get('ai_copilot_usage_roles') or []
        errors = cache.get('ai_copilot_usage_errors_total') or 0
        last_success_ts = cache.get('ai_copilot_last_success_ts') or 0
        last_error_ts = cache.get('ai_copilot_last_error_ts') or 0

        lines.append('# HELP ai_copilot_usage_total Total AI Copilot queries processed')
        lines.append('# TYPE ai_copilot_usage_total counter')
        lines.append(f'ai_copilot_usage_total {int(total)}')

        lines.append('# HELP ai_copilot_usage_denied_total Total AI Copilot queries denied (RBAC/Rate limit)')
        lines.append('# TYPE ai_copilot_usage_denied_total counter')
        lines.append(f'ai_copilot_usage_denied_total {int(denied)}')

        lines.append('# HELP ai_copilot_usage_errors_total Total AI Copilot errors')
        lines.append('# TYPE ai_copilot_usage_errors_total counter')
        lines.append(f'ai_copilot_usage_errors_total {int(errors)}')

        lines.append('# HELP ai_copilot_last_success_timestamp_seconds Last successful AI Copilot response time')
        lines.append('# TYPE ai_copilot_last_success_timestamp_seconds gauge')
        lines.append(f'ai_copilot_last_success_timestamp_seconds {float(last_success_ts)}')

        lines.append('# HELP ai_copilot_last_error_timestamp_seconds Last AI Copilot error time')
        lines.append('# TYPE ai_copilot_last_error_timestamp_seconds gauge')
        lines.append(f'ai_copilot_last_error_timestamp_seconds {float(last_error_ts)}')

        lines.append('# HELP ai_copilot_usage_role AI Copilot queries by role')
        lines.append('# TYPE ai_copilot_usage_role counter')
        for role in roles:
            val = cache.get(f'ai_copilot_usage_role:{role}') or 0
            # Sanitize role label value
            role_label = str(role).replace('"', '')
            lines.append(f'ai_copilot_usage_role{{role="{role_label}"}} {int(val)}')
    except Exception:
        # If cache backend doesn't support this, skip appending
        pass

    extra = ('\n'.join(lines) + '\n').encode('utf-8') if lines else b''
    return HttpResponse(base_output + extra, content_type=CONTENT_TYPE_LATEST)


@require_GET
@observability_auth_required
def copilot_metrics_json(request):
    """JSON endpoint for AI Copilot usage counters.

    Returns: { total: int, denied: int, roles: [{role: str, count: int}] }
    """
    try:
        total = cache.get('ai_copilot_usage_total') or 0
        denied = cache.get('ai_copilot_usage_denied_total') or 0
        roles = cache.get('ai_copilot_usage_roles') or []

        role_counts = []
        for role in roles:
            val = cache.get(f'ai_copilot_usage_role:{role}') or 0
            role_counts.append({
                'role': str(role),
                'count': int(val),
            })

        return JsonResponse({
            'success': True,
            'total': int(total),
            'denied': int(denied),
            'errors': int(errors),
            'last_success_ts': last_success_ts or None,
            'last_error_ts': last_error_ts or None,
            'roles': role_counts,
        })
    except Exception as exc:  # noqa: BLE001
        return JsonResponse({'success': False, 'error': str(exc)}, status=500)


# ============================================
# ADMIN DASHBOARD API ENDPOINTS
# ============================================

@require_GET
@observability_auth_required
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


@require_POST
@observability_auth_required
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


@require_GET
@observability_auth_required
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


@require_GET
@observability_auth_required
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


@require_GET
@observability_auth_required
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


# ============================================
# ADMIN DASHBOARD - Backend/System Management
# ============================================

@login_required
@user_passes_test(lambda u: u.is_staff or u.is_superuser or getattr(u, "role", None) == "ADMIN")
def admin_dashboard(request):
    """Backend admin dashboard for system management.
    
    Provides access to:
    - System statistics and health checks
    - User management and admin operations
    - Academic and financial management
    - Data export and reporting tools
    - Audit logs and activity tracking
    - Quick system actions and utilities
    """
    from django.contrib.auth.models import User, Group
    
    # Get system statistics
    total_users = User.objects.count()
    admin_count = User.objects.filter(is_staff=True).count()
    
    # Try to get student/teacher counts from custom user model if available
    try:
        from apps.accounts.models import User as CustomUser
        student_count = CustomUser.objects.filter(role='STUDENT').count()
        teacher_count = CustomUser.objects.filter(role='TEACHER').count()
    except (ImportError, AttributeError):
        student_count = 0
        teacher_count = 0
    
    # Get active sessions (approximate)
    from django.contrib.sessions.models import Session
    import datetime
    now = timezone.now()
    active_sessions = Session.objects.filter(expire_date__gte=now).count()
    sessions_24h = Session.objects.filter(expire_date__gte=now - datetime.timedelta(hours=24)).count()

    new_logins_24h = 0
    failed_logins_24h = 0
    failed_logins_by_role = []
    security_alerts_24h = 0
    access_denials_24h = 0
    try:
        from apps.compliance.models_audit import AccessLog, AuditLog
        cutoff_24h = now - datetime.timedelta(hours=24)
        login_paths = ["/authentication/login/", "/admin/login/"]
        login_attempts = AccessLog.objects.filter(
            resource__in=login_paths,
            request_method="POST",
            timestamp__gte=cutoff_24h,
        )
        new_logins_24h = login_attempts.filter(status__in=["302", "303"]).count()
        failed_logins = login_attempts.exclude(status__in=["302", "303"])
        failed_logins_24h = failed_logins.count()
        failed_logins_by_role = list(
            failed_logins.values(
                role=Coalesce("user__role", Value("Unknown"))
            ).annotate(count=Count("id")).order_by("-count")[:3]
        )

        security_alerts_24h = AuditLog.objects.filter(
            timestamp__gte=cutoff_24h
        ).filter(
            Q(action=AuditLog.Action.ACCESS_DENIED) | Q(sensitivity__in=["HIGH", "CRITICAL"])
        ).count()
        access_denials_24h = AuditLog.objects.filter(
            action=AuditLog.Action.ACCESS_DENIED,
            timestamp__gte=cutoff_24h,
        ).count()
    except Exception:
        new_logins_24h = 0
        failed_logins_24h = 0
        failed_logins_by_role = []
        security_alerts_24h = 0
        access_denials_24h = 0
    
    context = {
        'total_users': total_users,
        'admin_count': admin_count,
        'student_count': student_count,
        'teacher_count': teacher_count,
        'active_sessions': active_sessions,
        'sessions_24h': sessions_24h,
        'new_logins_24h': new_logins_24h,
        'failed_logins_24h': failed_logins_24h,
        'failed_logins_by_role': failed_logins_by_role,
        'security_alerts_24h': security_alerts_24h,
        'access_denials_24h': access_denials_24h,
    }
    
    return render(request, 'admin/admin_dashboard.html', context)
