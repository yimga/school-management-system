from django.urls import path

from .views import (
    at_risk_dashboard,
    at_risk_intervention_action,
    dashboard,
    executive_dashboard,
    forecaster_api,
    grading_deadlines,
    master_sheet,
    strategic_report,
)
from .views_governed import (
    decision_engagement_dashboard,
    decision_founder_dashboard,
    decision_intelligence_dashboard,
    decision_revenue_dashboard,
    decision_risk_dashboard,
    decision_school_health_dashboard,
    governed_query_export_csv,
    governed_query_export_json,
    governed_query_preview,
    governed_report_builder,
    governed_saved_report_run,
    governed_saved_report_save,
    governed_saved_reports_list,
)

app_name = "analytics"

urlpatterns = [
    path(
        "governed/report-builder/",
        governed_report_builder,
        name="governed_report_builder",
    ),
    path(
        "governed/query/preview/",
        governed_query_preview,
        name="governed_query_preview",
    ),
    path(
        "governed/export.csv",
        governed_query_export_csv,
        name="governed_query_export_csv",
    ),
    path(
        "governed/export.json",
        governed_query_export_json,
        name="governed_query_export_json",
    ),
    path(
        "governed/saved/",
        governed_saved_reports_list,
        name="governed_saved_reports_list",
    ),
    path(
        "governed/saved/new/",
        governed_saved_report_save,
        name="governed_saved_report_save",
    ),
    path(
        "governed/saved/<int:report_id>/run/",
        governed_saved_report_run,
        name="governed_saved_report_run",
    ),
    path(
        "decision-intelligence/",
        decision_intelligence_dashboard,
        name="decision_intelligence_dashboard",
    ),
    path(
        "decision/school-health/",
        decision_school_health_dashboard,
        name="decision_school_health_dashboard",
    ),
    path(
        "decision/revenue/",
        decision_revenue_dashboard,
        name="decision_revenue_dashboard",
    ),
    path(
        "decision/engagement/",
        decision_engagement_dashboard,
        name="decision_engagement_dashboard",
    ),
    path(
        "decision/risk/",
        decision_risk_dashboard,
        name="decision_risk_dashboard",
    ),
    path(
        "decision/founder/",
        decision_founder_dashboard,
        name="decision_founder_dashboard",
    ),
    path("", dashboard, name="dashboard"),
    path("master-sheet/", master_sheet, name="master_sheet"),
    path("deadlines/", grading_deadlines, name="deadlines"),
    path("strategic/", strategic_report, name="strategic_report"),
    path("api/forecaster/", forecaster_api, name="forecaster_api"),
    path("at-risk/", at_risk_dashboard, name="at_risk_dashboard"),
    path(
        "at-risk/intervention/",
        at_risk_intervention_action,
        name="at_risk_intervention_action",
    ),
    path("executive/", executive_dashboard, name="executive_dashboard"),
]
