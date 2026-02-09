from django.urls import path
from . import views_syllabus

app_name = "academics"

urlpatterns = [
    path("teacher/syllabi/", views_syllabus.teacher_syllabus_hub, name="teacher_syllabus_hub"),
    path("teacher/syllabi/<int:subject_assignment_id>/builder/", views_syllabus.syllabus_builder, name="syllabus_builder"),
    path("teacher/syllabi/<int:subject_assignment_id>/upload/", views_syllabus.syllabus_upload, name="syllabus_upload"),
    path("teacher/syllabi/<int:subject_assignment_id>/submit/", views_syllabus.syllabus_submit, name="syllabus_submit"),
    path("teacher/syllabi/<int:subject_assignment_id>/preview/", views_syllabus.syllabus_preview, name="syllabus_preview"),
    path("teacher/syllabi/<int:subject_assignment_id>/clone/", views_syllabus.syllabus_clone, name="syllabus_clone"),
    path("approval/syllabi/", views_syllabus.syllabus_approval_queue, name="syllabus_approval_queue"),
    path("approval/syllabi/<int:subject_assignment_id>/approve/", views_syllabus.syllabus_approve, name="syllabus_approve"),
    path("approval/syllabi/<int:subject_assignment_id>/reject/", views_syllabus.syllabus_reject, name="syllabus_reject"),
]
