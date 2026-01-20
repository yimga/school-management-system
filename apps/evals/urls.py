from django.urls import path

app_name = "evals"
from .views import (
    teacher_dashboard,
    teacher_marks_entry,
    teacher_marks_list,
    class_ranking_view,
    school_ranking_view,
    evaluation_admin,
    evaluation_evidence_upload,
    grade_import_template_view,
)

urlpatterns = [
    path("teacher/", teacher_dashboard, name="teacher_dashboard"),
    path("teacher/marks/entry/", teacher_marks_entry, name="teacher_marks_entry"),
    path("teacher/marks/", teacher_marks_list, name="teacher_marks_list"),

    # Staff/leadership dashboards
    path("rankings/class/", class_ranking_view, name="class_ranking"),
    path("rankings/school/", school_ranking_view, name="school_ranking"),
    path("admin/evaluations/", evaluation_admin, name="evaluation_admin"),
    path("admin/evaluations/evidence/", evaluation_evidence_upload, name="evaluation_evidence_upload"),
    path("grade-import-template/", grade_import_template_view, name="grade_import_template"),
]
