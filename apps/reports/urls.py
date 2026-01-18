from django.urls import path

from .views import (
    parent_download_annual_report,
    parent_download_term_report,
    parent_share_report,
    publish_term_results,
    report_share,
)

urlpatterns = [
    path("parent/report/<int:student_id>/", parent_download_term_report, name="parent_download_term_report"),
    path("parent/report/<int:student_id>/annual/", parent_download_annual_report, name="parent_download_annual_report"),
    path("parent/report/<int:student_id>/share/<str:report_type>/", parent_share_report, name="parent_share_report"),
    path("share/<str:token>/", report_share, name="report_share"),
    path("publish/", publish_term_results, name="publish_term_results"),
]

