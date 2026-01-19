from django.urls import path

from .views import (
    admissions_application_status,
    parent_dashboard,
    parent_child_results,
    portal_feature_page,
    portal_stats,
    teacher_dashboard_alias,
    student_portal_grades,
)

app_name = "portal"

urlpatterns = [
    path("parent/", parent_dashboard, name="parent_dashboard"),
    path("parent/results/<int:student_id>/", parent_child_results, name="parent_child_results"),
    path("features/<str:feature>/", portal_feature_page, name="portal_feature"),
    path("parent/stats/", portal_stats, name="portal_stats"),
    # Teacher dashboard alias for consistency
    path("teacher/", teacher_dashboard_alias, name="teacher_dashboard_alias"),
    # Semantic aliases for Phase 7 URL cleanup
    path("student-portal/grades/", student_portal_grades, name="student_portal_grades"),
    path("admissions/application-status/", admissions_application_status, name="admissions_application_status"),
]

