from django.urls import path

from .views import (
    dashboard,
    master_sheet,
    grading_deadlines,
    strategic_report,
    forecaster_api,
    at_risk_dashboard,
    executive_dashboard,
)

app_name = "analytics"

urlpatterns = [
    path("", dashboard, name="dashboard"),
    path("master-sheet/", master_sheet, name="master_sheet"),
    path("deadlines/", grading_deadlines, name="deadlines"),
    path("strategic/", strategic_report, name="strategic_report"),
    path("api/forecaster/", forecaster_api, name="forecaster_api"),
    path("at-risk/", at_risk_dashboard, name="at_risk_dashboard"),
    path("executive/", executive_dashboard, name="executive_dashboard"),
]
