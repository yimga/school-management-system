from django.urls import path
from .views import parent_download_term_report

urlpatterns = [
    path("parent/report/<int:student_id>/", parent_download_term_report, name="parent_download_term_report"),
]

