from django.urls import path

from . import views_syllabus, views_timetable, views_workflow

app_name = "academics"

urlpatterns = [
    path(
        "workflow/<str:workflow_key>/",
        views_workflow.WorkflowWizardView.as_view(),
        name="workflow_wizard",
    ),
    # Real, persisting timetable flow: generate -> review clashes -> publish (Stack A).
    path(
        "timetable/generate/",
        views_timetable.timetable_generate,
        name="timetable_generate",
    ),
    path(
        "timetable/<int:schedule_id>/review/",
        views_timetable.timetable_review,
        name="timetable_review",
    ),
    path(
        "timetable/<int:schedule_id>/publish/",
        views_timetable.timetable_publish,
        name="timetable_publish",
    ),
    path(
        "timetable/<int:schedule_id>/entries/<int:entry_id>/cancel/",
        views_timetable.timetable_cancel_entry,
        name="timetable_cancel_entry",
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
