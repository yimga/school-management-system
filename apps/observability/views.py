"""
Observability endpoints: /healthz and /metrics.
"""

from functools import wraps

from django.conf import settings
from django.http import HttpResponse, JsonResponse, HttpResponseForbidden
from django.db import connection
from django.views.decorators.http import require_GET, require_POST, require_http_methods
from django.shortcuts import render
from django.contrib.auth.decorators import login_required, user_passes_test
from django.utils import timezone
from django.db.models import Count, Q, Sum, Avg, Value
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
    """Internal health check including DB connectivity (RBAC/API-key protected)."""
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
def public_health(request):
    """Public health endpoint for load balancers and uptime checks.

    This endpoint intentionally does not require observability auth so it can be
    polled without credentials (expected by health check tests and external
    load balancers). It performs a lightweight DB check but avoids exposing
    any sensitive observability counters.
    """
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except Exception as exc:  # noqa: BLE001
        return JsonResponse({"status": "error", "error": str(exc)}, status=500)

    return JsonResponse({"status": "healthy"})


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
        errors = cache.get('ai_copilot_usage_errors_total') or 0
        last_success_ts = cache.get('ai_copilot_last_success_ts') or 0
        last_error_ts = cache.get('ai_copilot_last_error_ts') or 0
        roles = cache.get('ai_copilot_usage_roles') or []

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
        errors = cache.get('ai_copilot_usage_errors_total') or 0
        last_success_ts = cache.get('ai_copilot_last_success_ts') or 0
        last_error_ts = cache.get('ai_copilot_last_error_ts') or 0
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
            'last_success_ts': float(last_success_ts) if last_success_ts else None,
            'last_error_ts': float(last_error_ts) if last_error_ts else None,
            'roles': role_counts,
        })
    except Exception as exc:  # noqa: BLE001
        return JsonResponse({
            'success': True,
            'total': 0,
            'denied': 0,
            'errors': 0,
            'last_success_ts': None,
            'last_error_ts': None,
            'roles': [],
            'warning': str(exc),
        })


# ============================================
# ADMIN DASHBOARD API ENDPOINTS
# ============================================

@require_http_methods(["GET", "HEAD"])
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
@login_required
def api_notifications_mark_all_read(request):
    """Mark all notifications for the current user as read."""
    try:
        from apps.finance.models import Notification

        user = request.user
        qs = Notification.objects.filter(
            Q(recipient=user) | Q(created_by=user)
        ).filter(is_read=False)
        updated = qs.update(is_read=True)
        return JsonResponse({
            "status": "success",
            "message": "All notifications marked as read",
            "count": updated
        })
    except Exception as exc:
        return JsonResponse({
            "status": "error",
            "error": str(exc)
        }, status=500)


@require_GET
@login_required
def api_notifications(request):
    """API endpoint to fetch recent notifications.
    
    Returns a list of recent system notifications and alerts.
    """
    try:
        from apps.finance.models import Notification

        user = request.user
        notifications_qs = Notification.objects.filter(
            Q(recipient=user) | Q(created_by=user)
        ).order_by('-created_at')[:50]
        mapped = []
        for notif in notifications_qs:
            notif_type = "info"
            if notif.severity == Notification.Severity.ALERT:
                notif_type = "alert"
            elif notif.severity == Notification.Severity.WARNING:
                notif_type = "warning"

            mapped.append({
                "id": notif.id,
                "title": notif.title,
                "message": notif.message,
                "type": notif_type,
                "category": notif.severity,
                "is_read": notif.is_read,
                "created_at": notif.created_at.isoformat(),
                "timestamp": notif.created_at.isoformat(),
                "link": notif.link,
            })

        return JsonResponse({
            "status": "success",
            "notifications": mapped,
            "count": len(mapped)
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
        from django.contrib.admin.models import LogEntry

        page = int(request.GET.get('page', 1))
        per_page = 10

        logs = LogEntry.objects.select_related("user", "content_type").order_by("-action_time")
        total = logs.count()
        logs = logs[(page - 1) * per_page: page * per_page]

        activities = []
        for entry in logs:
            if entry.is_addition():
                action_type = "add"
            elif entry.is_change():
                action_type = "change"
            elif entry.is_deletion():
                action_type = "delete"
            else:
                action_type = "activity"

            activities.append({
                "id": entry.id,
                "type": action_type,
                "title": entry.object_repr,
                "description": entry.get_change_message() or action_type.title(),
                "timestamp": entry.action_time.isoformat(),
                "user": getattr(entry.user, "username", None),
            })

        return JsonResponse({
            "status": "success",
            "activities": activities,
            "count": len(activities),
            "total": total,
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
        from apps.people.models import StudentProfile, TeacherAttendance
        from apps.academics.models import Classroom
        from apps.finance.models import Invoice, Payment
        from apps.evals.models import Evaluation

        # Enrollment by classroom
        classrooms = Classroom.objects.annotate(
            total=Count("students", filter=Q(students__is_active=True))
        ).order_by("-total")[:6]
        enrollment_labels = [c.name for c in classrooms]
        enrollment_data = [c.total for c in classrooms]
        enrollment = {
            "labels": enrollment_labels,
            "datasets": [{
                "label": "Active students",
                "data": enrollment_data,
                "borderColor": "#ff6a88",
                "backgroundColor": "rgba(255, 106, 136, 0.1)",
                "tension": 0.4,
                "fill": True,
                "pointRadius": 4,
                "pointHoverRadius": 6,
            }],
        }

        # Fee collection
        invoiced = Invoice.objects.exclude(status=Invoice.Status.VOID).aggregate(total=Sum("total_amount")).get("total") or 0
        paid = Payment.objects.filter(status="completed").aggregate(total=Sum("amount")).get("total") or 0
        overdue_amount = Invoice.objects.filter(status=Invoice.Status.OVERDUE).aggregate(total=Sum("balance_amount")).get("total") or 0
        fee_collection = {
            "labels": ["Paid", "Pending", "Overdue"],
            "datasets": [{
                "data": [
                    float(paid),
                    float(max(invoiced - paid, 0)),
                    float(overdue_amount or 0),
                ],
                "backgroundColor": ['#2dd4bf', '#9b6bff', '#ff6a88'],
            }],
        }

        # Performance by subject (exam score average)
        subject_scores = (
            Evaluation.objects.exclude(exam_score__isnull=True)
            .values("subject_assignment__subject__name")
            .annotate(avg=Avg("exam_score"))
            .order_by("-avg")[:6]
        )
        perf_labels = [row["subject_assignment__subject__name"] or "Subject" for row in subject_scores]
        perf_data = [round(float(row["avg"]), 1) for row in subject_scores]
        performance = {
            "labels": perf_labels,
            "datasets": [{
                "label": "Average Grade",
                "data": perf_data,
                "borderColor": "#9b6bff",
                "backgroundColor": "rgba(155, 107, 255, 0.1)",
                "fill": True,
            }],
        }

        # Attendance snapshot for the past 7 days
        today = timezone.localdate()
        window = TeacherAttendance.objects.filter(date__range=(today - __import__('datetime').timedelta(days=6), today))
        attendance_counts = {
            "Present": window.filter(status=TeacherAttendance.Status.PRESENT).count(),
            "Absent": window.filter(status=TeacherAttendance.Status.ABSENT).count(),
            "Late": window.filter(status=TeacherAttendance.Status.LATE).count(),
            "On leave": window.filter(status=TeacherAttendance.Status.ON_LEAVE).count(),
        }
        attendance = {
            "labels": list(attendance_counts.keys()),
            "datasets": [{
                "data": list(attendance_counts.values()),
                "backgroundColor": ['#2dd4bf', '#ff6a88', '#9b6bff', '#f59e0b'],
            }],
        }

        return JsonResponse({
            "status": "success",
            "enrollment": enrollment,
            "feeCollection": fee_collection,
            "performance": performance,
            "attendance": attendance,
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
    
    # Try to get student/teacher/parent counts from custom user model if available
    try:
        from apps.accounts.models import User as CustomUser
        student_count = CustomUser.objects.filter(role='STUDENT').count()
        teacher_count = CustomUser.objects.filter(role='TEACHER').count()
        parent_count = CustomUser.objects.filter(role='PARENT').count()
    except (ImportError, AttributeError):
        student_count = 0
        teacher_count = 0
        parent_count = 0
    
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
    
    # System info (dynamic, shared with config/admin.py dashboard)
    import sys
    import django as _django
    from django.db import connection as _conn
    from django.conf import settings as _settings
    _db_vendor = _conn.vendor
    _db_display = {'sqlite': 'SQLite3', 'postgresql': 'PostgreSQL', 'mysql': 'MySQL', 'oracle': 'Oracle'}.get(_db_vendor, _db_vendor.title())

    context = {
        'total_users': total_users,
        'admin_count': admin_count,
        'student_count': student_count,
        'teacher_count': teacher_count,
        'parent_count': parent_count,
        'active_sessions': active_sessions,
        'sessions_24h': sessions_24h,
        'new_logins_24h': new_logins_24h,
        'failed_logins_24h': failed_logins_24h,
        'failed_logins_by_role': failed_logins_by_role,
        'security_alerts_24h': security_alerts_24h,
        'access_denials_24h': access_denials_24h,
        'django_version': _django.get_version(),
        'python_version': f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        'db_engine_display': _db_display,
        'is_debug': _settings.DEBUG,
        'admin_palette': {},
        'preview_data': None,
    }
    
    return render(request, 'admin/admin_dashboard.html', context)
