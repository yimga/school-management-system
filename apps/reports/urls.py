from django.urls import path

from .views import (
    parent_download_annual_report,
    parent_download_annual_report_csv,
    parent_download_term_report,
    parent_download_term_report_csv,
    parent_share_report,
    promotion_preview,
    publish_term_results,
    regulatory_export,
    report_share,
    statistical_return,
    verify_report_hash,
)

app_name = "reports"

urlpatterns = [
    path(
        "parent/report/<int:student_id>/",
        parent_download_term_report,
        name="parent_download_term_report",
    ),
    path(
        "parent/report/<int:student_id>/csv/",
        parent_download_term_report_csv,
        name="parent_download_term_report_csv",
    ),
    path(
        "parent/report/<int:student_id>/annual/",
        parent_download_annual_report,
        name="parent_download_annual_report",
    ),
    path(
        "parent/report/<int:student_id>/annual/csv/",
        parent_download_annual_report_csv,
        name="parent_download_annual_report_csv",
    ),
    path(
        "parent/report/<int:student_id>/share/<str:report_type>/",
        parent_share_report,
        name="parent_share_report",
    ),
    path("share/<str:token>/", report_share, name="report_share"),  # rbac-allow: token in URL is the auth (single-use report share link)
    path("verify-hash/", verify_report_hash, name="verify_report_hash"),  # rbac-allow: public report-hash verifier (read-only authenticity check)
    path("publish/", publish_term_results, name="publish_term_results"),
    path("statistical-return/", statistical_return, name="statistical_return"),
    path("promotion-preview/", promotion_preview, name="promotion_preview"),
    path("regulatory-export/", regulatory_export, name="regulatory_export"),
]
