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
from apps.compliance.views_gdpr import data_portability_export, erasure_request_view
from apps.compliance.views_queue import (
    approve_erase,
    complete_erase,
    complete_export,
    data_rights_queue,
    reject_erase,
)
from apps.compliance.views_ferpa import ferpa_disclosure_detail
from apps.compliance.views_data_quality import data_quality_center

app_name = "compliance"

urlpatterns = [
    # Dashboard view
    path("dashboard/", ComplianceDashboardView.as_view(), name="dashboard"),
    # Wave 5 (v2.76): Data Quality Center — tenant-scoped completeness checks.
    path("data-quality/", data_quality_center, name="data_quality_center"),
    # Pass 9.C: operator-facing GDPR/FERPA queue with SLA tracking.
    path("data-rights/queue/", data_rights_queue, name="data_rights_queue"),
    # Pass 9.E: single-disclosure detail view for FERPA §99.32 evidence trail.
    path(
        "ferpa/disclosure/<int:pk>/",
        ferpa_disclosure_detail,
        name="ferpa_disclosure_detail",
    ),
    path("data-rights/erase/<int:pk>/approve/", approve_erase, name="erase_approve"),
    path("data-rights/erase/<int:pk>/reject/", reject_erase, name="erase_reject"),
    path("data-rights/erase/<int:pk>/complete/", complete_erase, name="erase_complete"),
    path("data-rights/export/<int:pk>/complete/", complete_export, name="export_complete"),
    # API endpoints
    path("api/overview/", ComplianceOverviewAPI.as_view(), name="api_overview"),
    path(
        "api/regional-metrics/",
        RegionalMetricsAPI.as_view(),
        name="api_regional_metrics",
    ),
    path(
        "api/check-statistics/",
        CheckStatisticsAPI.as_view(),
        name="api_check_statistics",
    ),
    path(
        "api/audit-log-summary/",
        AuditLogSummaryAPI.as_view(),
        name="api_audit_log_summary",
    ),
    path(
        "api/document-status/", DocumentStatusAPI.as_view(), name="api_document_status"
    ),
    path("api/timeline-data/", TimelineDataAPI.as_view(), name="api_timeline_data"),
    path(
        "api/regional-comparison/",
        RegionalComparisonAPI.as_view(),
        name="api_regional_comparison",
    ),
    path("api/critical-items/", CriticalItemsAPI.as_view(), name="api_critical_items"),
    path("api/mute-threats/", mute_threats, name="api_mute_threats"),
    # Phase 4: Compliance reporting
    path("reports/", include("apps.compliance.urls_reporting")),
    # Phase Compliance optional: GDPR data portability (MFA required) and erasure request
    path("gdpr/export/", data_portability_export, name="data_portability_export"),
    path("gdpr/erasure-request/", erasure_request_view, name="erasure_request"),
]
