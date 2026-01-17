from django.urls import path
from .views import parent_dashboard, parent_child_results

urlpatterns = [
    path("parent/", parent_dashboard, name="parent_dashboard"),
    path("parent/results/<int:student_id>/", parent_child_results, name="parent_child_results"),
]

