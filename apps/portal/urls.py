from django.urls import path

from .views import (
    parent_dashboard,
    parent_child_results,
    portal_feature_page,
    portal_stats,
    parent_finance,
    link_child,
    link_child_wizard,
    claim_invite,
    teacher_dashboard_alias,
    teacher_attendance_view,
    teacher_pay_history,
    teacher_leave,
    teacher_attendance_export,
    student_portal_grades,
    admissions_application_status,
    portal_syllabus,
    preview_student_syllabus,
    preview_communication_test,
    teacher_onboarding_wizard,
    student_onboarding_wizard,
)

app_name = "portal"

urlpatterns = [
    # Home and portal entry
    path("", parent_dashboard, name="home"),
    path("home/", parent_dashboard, name="portal_home"),
    
    # Parent portal
    path("parent/", parent_dashboard, name="parent_dashboard"),
    path("parent/results/<int:student_id>/", parent_child_results, name="parent_child_results"),
    path("parent/link-child/", link_child_wizard, name="link_child"),  # New wizard as default
    path("parent/link-child/legacy/", link_child, name="link_child_legacy"),  # Keep old view for compatibility
    path("parent/claim-invite/", claim_invite, name="claim_invite"),
    path("parent/claim-invite/<str:token>/", claim_invite, name="claim_invite_token"),
    path("parent/finance/", parent_finance, name="parent_finance"),
    # Backwards compatibility: older templates and tests expect 'parent_performance'
    path("parent/performance/", parent_child_results, name="parent_performance"),
    path("features/<str:feature>/", portal_feature_page, name="portal_feature"),
    path("parent/stats/", portal_stats, name="portal_stats"),
    path("syllabus/", portal_syllabus, name="portal_syllabus"),
    path("preview/syllabus/", preview_student_syllabus, name="preview_syllabus"),
    path("preview/communication/", preview_communication_test, name="preview_communication_test"),
    
    # Teacher dashboard
    path("teacher/", teacher_dashboard_alias, name="teacher_dashboard_alias"),
    path("teacher/onboarding/", teacher_onboarding_wizard, name="teacher_onboarding"),
    path("teacher/attendance/", teacher_attendance_view, name="teacher_attendance"),
    path("teacher/attendance/export/", teacher_attendance_export, name="teacher_attendance_export"),
    path("teacher/pay-history/", teacher_pay_history, name="teacher_pay_history"),
    path("teacher/leave/", teacher_leave, name="teacher_leave"),
    
    # Student onboarding
    path("student/onboarding/", student_onboarding_wizard, name="student_onboarding"),
    
    # Semantic aliases for Phase 7 URL cleanup
    path("student-portal/grades/", student_portal_grades, name="student_portal_grades"),
    path("admissions/application-status/", admissions_application_status, name="admissions_application_status"),
]
