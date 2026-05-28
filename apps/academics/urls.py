from django.urls import path

from django.views.generic import TemplateView

from . import views_syllabus, views_workflow
from .views_timetable_solver import TimetableBuildView

app_name = "academics"

urlpatterns = [
    path(
        "workflow/<str:workflow_key>/",
        views_workflow.WorkflowWizardView.as_view(),
        name="workflow_wizard",
    ),
    # v4.00.13: timetable build (UI + POST endpoint).
    path(
        "timetable/build/",
        TimetableBuildView.as_view(),
        name="timetable_build",
    ),
    path(
        "timetable/build/ui/",
        TemplateView.as_view(template_name="portal/timetable_build.html"),
        name="timetable_build_ui",
    ),
    # v4.00.13: CA-mark input UI for certification candidates.
    path(
        "certification/ca-marks/<int:candidate_id>/",
        __import__("apps.academics.views_ca_marks", fromlist=["CAMarksInputView"]).CAMarksInputView.as_view(),
        name="ca_marks_input",
    ),
    path(
        "teacher/syllabi/",
        views_syllabus.teacher_syllabus_hub,
        name="teacher_syllabus_hub",
    ),
    path(
        "teacher/syllabi/<int:subject_assignment_id>/builder/",
        views_syllabus.syllabus_builder,
        name="syllabus_builder",
    ),
    path(
        "teacher/syllabi/<int:subject_assignment_id>/upload/",
        views_syllabus.syllabus_upload,
        name="syllabus_upload",
    ),
    path(
        "teacher/syllabi/<int:subject_assignment_id>/submit/",
        views_syllabus.syllabus_submit,
        name="syllabus_submit",
    ),
    path(
        "teacher/syllabi/<int:subject_assignment_id>/preview/",
        views_syllabus.syllabus_preview,
        name="syllabus_preview",
    ),
    path(
        "teacher/syllabi/<int:subject_assignment_id>/clone/",
        views_syllabus.syllabus_clone,
        name="syllabus_clone",
    ),
    path(
        "approval/syllabi/",
        views_syllabus.syllabus_approval_queue,
        name="syllabus_approval_queue",
    ),
    path(
        "approval/syllabi/<int:subject_assignment_id>/approve/",
        views_syllabus.syllabus_approve,
        name="syllabus_approve",
    ),
    path(
        "approval/syllabi/<int:subject_assignment_id>/reject/",
        views_syllabus.syllabus_reject,
        name="syllabus_reject",
    ),
]
