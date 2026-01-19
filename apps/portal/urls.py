from django.urls import path

from .views import (
    parent_dashboard,
    parent_child_results,
    portal_feature_page,
    portal_stats,
)

urlpatterns = [
    path("parent/", parent_dashboard, name="parent_dashboard"),
    path("parent/results/<int:student_id>/", parent_child_results, name="parent_child_results"),
    path("features/<str:feature>/", portal_feature_page, name="portal_feature"),
    path("parent/stats/", portal_stats, name="portal_stats"),
]

