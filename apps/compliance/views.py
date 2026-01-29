"""Compliance Dashboard Views for Phase 1.2.9"""
from django.shortcuts import render
from django.http import JsonResponse
from django.views import View
from django.contrib.auth.decorators import login_required
from django.utils.decorators import method_decorator
from django.views.decorators.http import require_http_methods
from django_ratelimit.decorators import ratelimit
from apps.compliance.analytics import ComplianceAnalytics


class ComplianceDashboardView(View):
    """Main compliance dashboard view."""
    
    @method_decorator(login_required)
    def get(self, request):
        """Render compliance dashboard."""
        analytics = ComplianceAnalytics()
        
        from apps.siteconfig.dashboard_views import load_dashboard_layout_settings, _can_customize
        from apps.siteconfig.models_dashboard import get_dashboard_widget_metadata
        from django.urls import reverse
        from django.utils.safestring import mark_safe
        import json
        
        dashboard_settings = load_dashboard_layout_settings(request.user, "compliance")
        allow_custom_layout = _can_customize(request.user)
        dashboard_layout_url = reverse("api:dashboard-layout", kwargs={"page": "compliance"})
        available_sidebar_items = [
            {"id": "compliance-home", "label": "Compliance Home", "url": reverse("compliance:dashboard"), "icon": "bi-shield-check"},
            {"id": "compliance-audit", "label": "Audit Trail", "url": reverse("compliance:compliance_reporting:audit_trail"), "icon": "bi-file-text"},
            {"id": "compliance-access", "label": "Data Access", "url": reverse("compliance:compliance_reporting:data_access"), "icon": "bi-key"},
            {"id": "compliance-permissions", "label": "Permissions", "url": reverse("compliance:compliance_reporting:permissions"), "icon": "bi-lock"},
            {"id": "compliance-integrity", "label": "Integrity Check", "url": reverse("compliance:compliance_reporting:integrity_check"), "icon": "bi-check-circle"},
            {"id": "compliance-anomalies", "label": "Anomalies", "url": reverse("compliance:compliance_reporting:anomalies"), "icon": "bi-exclamation-triangle"},
        ]
        widget_meta_json = mark_safe(json.dumps(get_dashboard_widget_metadata()))
        
        context = {
            'overview': analytics.get_compliance_overview(),
            'regional_metrics': analytics.get_regional_metrics(),
            'check_statistics': analytics.get_check_statistics(),
            'document_status': analytics.get_document_status(),
            'critical_items': analytics.get_critical_items(),
            'regional_comparison': analytics.get_regional_comparison(),
            'allow_custom_layout': allow_custom_layout,
            'dashboard_settings': dashboard_settings,
            'dashboard_layout_url': dashboard_layout_url,
            'available_sidebar_items': available_sidebar_items,
            'widget_meta_json': widget_meta_json,
        }
        return render(request, 'compliance/dashboard.html', context)


@method_decorator(login_required, name='dispatch')
@method_decorator(ratelimit(key='user', rate='30/m', method='GET', block=True), name='dispatch')
class ComplianceOverviewAPI(View):
    """API endpoint for compliance overview data."""
    
    def get(self, request):
        """Get compliance overview metrics."""
        analytics = ComplianceAnalytics()
        data = analytics.get_compliance_overview()
        return JsonResponse(data)


@method_decorator(login_required, name='dispatch')
@method_decorator(ratelimit(key='user', rate='30/m', method='GET', block=True), name='dispatch')
class RegionalMetricsAPI(View):
    """API endpoint for regional compliance metrics."""
    
    def get(self, request):
        """Get regional metrics."""
        analytics = ComplianceAnalytics()
        data = analytics.get_regional_metrics()
        return JsonResponse(data)


@method_decorator(login_required, name='dispatch')
class CheckStatisticsAPI(View):
    """API endpoint for compliance check statistics."""
    
    def get(self, request):
        """Get check statistics."""
        analytics = ComplianceAnalytics()
        data = analytics.get_check_statistics()
        return JsonResponse(data)


@method_decorator(login_required, name='dispatch')
class AuditLogSummaryAPI(View):
    """API endpoint for audit log summary."""
    
    def get(self, request):
        """Get audit log summary."""
        days = int(request.GET.get('days', 30))
        analytics = ComplianceAnalytics()
        data = analytics.get_audit_log_summary(days=days)
        return JsonResponse(data)


@method_decorator(login_required, name='dispatch')
class DocumentStatusAPI(View):
    """API endpoint for document status."""
    
    def get(self, request):
        """Get document status."""
        analytics = ComplianceAnalytics()
        data = analytics.get_document_status()
        return JsonResponse(data)


@method_decorator(login_required, name='dispatch')
class TimelineDataAPI(View):
    """API endpoint for timeline data."""
    
    def get(self, request):
        """Get timeline data."""
        days = int(request.GET.get('days', 90))
        analytics = ComplianceAnalytics()
        data = analytics.get_timeline_data(days=days)
        return JsonResponse(data, safe=False)


@method_decorator(login_required, name='dispatch')
class RegionalComparisonAPI(View):
    """API endpoint for regional comparison."""
    
    def get(self, request):
        """Get regional comparison."""
        analytics = ComplianceAnalytics()
        data = analytics.get_regional_comparison()
        return JsonResponse(data, safe=False)


@method_decorator(login_required, name='dispatch')
class CriticalItemsAPI(View):
    """API endpoint for critical items."""
    
    def get(self, request):
        """Get critical items."""
        analytics = ComplianceAnalytics()
        data = analytics.get_critical_items()
        return JsonResponse(data, safe=False)
