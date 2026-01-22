"""URLs for Compliance App Dashboard"""
from django.urls import path, include
from apps.compliance.views import (
    ComplianceDashboardView,
    ComplianceOverviewAPI,
    RegionalMetricsAPI,
    CheckStatisticsAPI,
    AuditLogSummaryAPI,
    DocumentStatusAPI,
    TimelineDataAPI,
    RegionalComparisonAPI,
    CriticalItemsAPI,
)
from apps.compliance.views_api import mute_threats

app_name = 'compliance'

urlpatterns = [
    # Dashboard view
    path('dashboard/', ComplianceDashboardView.as_view(), name='dashboard'),
    
    # API endpoints
    path('api/overview/', ComplianceOverviewAPI.as_view(), name='api_overview'),
    path('api/regional-metrics/', RegionalMetricsAPI.as_view(), name='api_regional_metrics'),
    path('api/check-statistics/', CheckStatisticsAPI.as_view(), name='api_check_statistics'),
    path('api/audit-log-summary/', AuditLogSummaryAPI.as_view(), name='api_audit_log_summary'),
    path('api/document-status/', DocumentStatusAPI.as_view(), name='api_document_status'),
    path('api/timeline-data/', TimelineDataAPI.as_view(), name='api_timeline_data'),
    path('api/regional-comparison/', RegionalComparisonAPI.as_view(), name='api_regional_comparison'),
    path('api/critical-items/', CriticalItemsAPI.as_view(), name='api_critical_items'),
    path('api/mute-threats/', mute_threats, name='api_mute_threats'),
    
    # Phase 4: Compliance reporting
    path('reports/', include('apps.compliance.urls_reporting')),
]
