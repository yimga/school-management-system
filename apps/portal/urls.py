from django.urls import path

from .views import (
    parent_dashboard,
    parent_child_results,
    portal_feature_page,
    portal_stats,
    link_child,
    claim_invite,
    teacher_dashboard_alias,
    teacher_attendance_view,
    teacher_pay_history,
    teacher_leave,
    student_portal_grades,
    admissions_application_status,
)

app_name = "portal"

urlpatterns = [
    path("parent/", parent_dashboard, name="parent_dashboard"),
    path("parent/results/<int:student_id>/", parent_child_results, name="parent_child_results"),
    path("parent/link-child/", link_child, name="link_child"),
    path("parent/claim-invite/", claim_invite, name="claim_invite"),
    path("parent/claim-invite/<str:token>/", claim_invite, name="claim_invite_token"),
    path("features/<str:feature>/", portal_feature_page, name="portal_feature"),
    path("parent/stats/", portal_stats, name="portal_stats"),
    # Teacher dashboard alias for consistency
    path("teacher/", teacher_dashboard_alias, name="teacher_dashboard_alias"),
    path("teacher/attendance/", teacher_attendance_view, name="teacher_attendance"),
    path("teacher/pay-history/", teacher_pay_history, name="teacher_pay_history"),
    path("teacher/leave/", teacher_leave, name="teacher_leave"),
    # Semantic aliases for Phase 7 URL cleanup
    path("student-portal/grades/", student_portal_grades, name="student_portal_grades"),
    path("admissions/application-status/", admissions_application_status, name="admissions_application_status"),
]
