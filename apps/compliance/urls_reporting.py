"""
Phase 4: Compliance Reporting URLs

URL patterns for compliance reports:
- Audit trail reports
- Data access summaries
- Permission overviews
- Integrity checks
- Anomaly detection
- Export functionality
- Dashboard & metrics
"""

from django.urls import path
from . import views_reporting, views_dashboard

app_name = 'compliance_reporting'

urlpatterns = [
    # Dashboard
    path('dashboard/', views_dashboard.ComplianceDashboardView.as_view(), name='dashboard'),
    
    # Report views
    path('audit-trail/', views_reporting.AuditTrailReportView.as_view(), name='audit_trail'),
    path('data-access/', views_reporting.DataAccessReportView.as_view(), name='data_access'),
    path('permissions/', views_reporting.PermissionOverviewView.as_view(), name='permissions'),
    path('integrity-check/', views_reporting.IntegrityCheckReportView.as_view(), name='integrity_check'),
    path('anomalies/', views_reporting.AnomalyDetectionView.as_view(), name='anomalies'),
    
    # Export
    path('export/', views_reporting.ExportComplianceReportView.as_view(), name='export'),
]
