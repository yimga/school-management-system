"""Compliance Dashboard Views for Phase 1.2.9"""

from django.shortcuts import render
from django.http import JsonResponse
from django.views import View
from django.contrib.auth.decorators import login_required, user_passes_test
from django.utils.decorators import method_decorator
from django_ratelimit.decorators import ratelimit
from apps.compliance.analytics import ComplianceAnalytics
from apps.compliance.auth_utils import is_admin_or_staff


class ComplianceDashboardView(View):
    """Main compliance dashboard view. RBAC: staff or ADMIN/LEADERSHIP only."""

    @method_decorator(login_required)
    @method_decorator(user_passes_test(is_admin_or_staff))
    def get(self, request):
        """Render compliance dashboard."""
        analytics = ComplianceAnalytics()

        from apps.accounts.utils import get_dashboard_context
        from django.urls import reverse

        dashboard_context = get_dashboard_context(request.user, "compliance")
        dashboard_settings = dashboard_context.get("dashboard_settings", {})
        allow_custom_layout = dashboard_context.get("allow_custom_layout", False)
        dashboard_layout_url = dashboard_context.get("dashboard_layout_url", "")
        widget_meta_json = dashboard_context.get("widget_meta_json", "")
        available_sidebar_items = [
            {
                "id": "compliance-home",
                "label": "Compliance Home",
                "url": reverse("compliance:dashboard"),
                "icon": "bi-shield-check",
            },
            {
                "id": "compliance-audit",
                "label": "Audit Trail",
                "url": reverse("compliance:compliance_reporting:audit_trail"),
                "icon": "bi-file-text",
            },
            {
                "id": "compliance-access",
                "label": "Data Access",
                "url": reverse("compliance:compliance_reporting:data_access"),
                "icon": "bi-key",
            },
            {
                "id": "compliance-permissions",
                "label": "Permissions",
                "url": reverse("compliance:compliance_reporting:permissions"),
                "icon": "bi-lock",
            },
            {
                "id": "compliance-integrity",
                "label": "Integrity Check",
                "url": reverse("compliance:compliance_reporting:integrity_check"),
                "icon": "bi-check-circle",
            },
            {
                "id": "compliance-anomalies",
                "label": "Anomalies",
                "url": reverse("compliance:compliance_reporting:anomalies"),
                "icon": "bi-exclamation-triangle",
            },
        ]

        context = {
            "overview": analytics.get_compliance_overview(),
            "regional_metrics": analytics.get_regional_metrics(),
            "check_statistics": analytics.get_check_statistics(),
            "document_status": analytics.get_document_status(),
            "critical_items": analytics.get_critical_items(),
            "regional_comparison": analytics.get_regional_comparison(),
            "allow_custom_layout": allow_custom_layout,
            "dashboard_settings": dashboard_settings,
            "dashboard_layout_url": dashboard_layout_url,
            "available_sidebar_items": available_sidebar_items,
            "widget_meta_json": widget_meta_json,
        }
        return render(request, "compliance/dashboard.html", context)


@method_decorator(login_required, name="dispatch")
@method_decorator(user_passes_test(is_admin_or_staff), name="dispatch")
@method_decorator(
    ratelimit(key="user", rate="30/m", method="GET", block=True), name="dispatch"
)
class ComplianceOverviewAPI(View):
    """API endpoint for compliance overview data (staff/ADMIN/LEADERSHIP only)."""

    def get(self, request):
        analytics = ComplianceAnalytics()
        data = analytics.get_compliance_overview()
        return JsonResponse(data)


@method_decorator(login_required, name="dispatch")
@method_decorator(user_passes_test(is_admin_or_staff), name="dispatch")
@method_decorator(
    ratelimit(key="user", rate="30/m", method="GET", block=True), name="dispatch"
)
class RegionalMetricsAPI(View):
    """API endpoint for regional compliance metrics (staff/ADMIN/LEADERSHIP only)."""

    def get(self, request):
        analytics = ComplianceAnalytics()
        data = analytics.get_regional_metrics()
        return JsonResponse(data)


@method_decorator(login_required, name="dispatch")
@method_decorator(user_passes_test(is_admin_or_staff), name="dispatch")
class CheckStatisticsAPI(View):
    """API endpoint for compliance check statistics (staff/ADMIN/LEADERSHIP only)."""

    def get(self, request):
        analytics = ComplianceAnalytics()
        data = analytics.get_check_statistics()
        return JsonResponse(data)


@method_decorator(login_required, name="dispatch")
@method_decorator(user_passes_test(is_admin_or_staff), name="dispatch")
class AuditLogSummaryAPI(View):
    """API endpoint for audit log summary."""

    def get(self, request):
        """Get audit log summary."""
        days = int(request.GET.get("days", 30))
        analytics = ComplianceAnalytics()
        data = analytics.get_audit_log_summary(days=days)
        return JsonResponse(data)


@method_decorator(login_required, name="dispatch")
@method_decorator(user_passes_test(is_admin_or_staff), name="dispatch")
class DocumentStatusAPI(View):
    """API endpoint for document status (staff/ADMIN/LEADERSHIP only)."""

    def get(self, request):
        analytics = ComplianceAnalytics()
        data = analytics.get_document_status()
        return JsonResponse(data)


@method_decorator(login_required, name="dispatch")
@method_decorator(user_passes_test(is_admin_or_staff), name="dispatch")
class TimelineDataAPI(View):
    """API endpoint for timeline data (staff/ADMIN/LEADERSHIP only)."""

    def get(self, request):
        days = int(request.GET.get("days", 90))
        analytics = ComplianceAnalytics()
        data = analytics.get_timeline_data(days=days)
        return JsonResponse(data, safe=False)


@method_decorator(login_required, name="dispatch")
@method_decorator(user_passes_test(is_admin_or_staff), name="dispatch")
class RegionalComparisonAPI(View):
    """API endpoint for regional comparison (staff/ADMIN/LEADERSHIP only)."""

    def get(self, request):
        """Get regional comparison."""
        analytics = ComplianceAnalytics()
        data = analytics.get_regional_comparison()
        return JsonResponse(data, safe=False)


@method_decorator(login_required, name="dispatch")
@method_decorator(user_passes_test(is_admin_or_staff), name="dispatch")
class CriticalItemsAPI(View):
    """API endpoint for critical items (staff/ADMIN/LEADERSHIP only)."""

    def get(self, request):
        analytics = ComplianceAnalytics()
        data = analytics.get_critical_items()
        return JsonResponse(data, safe=False)
