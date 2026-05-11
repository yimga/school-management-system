from django.urls import path

app_name = "evals"
from .views import (
    teacher_dashboard,
    teacher_workflow_center,
    teacher_marks_entry,
    teacher_marks_list,
    class_ranking_view,
    school_ranking_view,
    evaluation_admin,
    evaluation_evidence_upload,
    grade_import_template_view,
    grade_import_upload_view,
    compliance_dashboard_view,
    extend_deadline_view,
    grade_import_preview_api,
    grade_import_apply_api,
    audit_trail_view,
    resolve_offline_conflict_view,
    import_job_monitor_view,
    grade_approval_list,
    grade_approval_detail,
    rosetta_grade_preview_api,
)
from .views_drilldown import evaluation_drilldown

urlpatterns = [
    # Pass 9.E: per-evaluation drill-down with GradeAudit trail.
    path("evaluation/<int:pk>/", evaluation_drilldown, name="evaluation_drilldown"),
    path("teacher/", teacher_dashboard, name="teacher_dashboard"),
    path("teacher/workflow/", teacher_workflow_center, name="teacher_workflow"),
    path("teacher/marks/entry/", teacher_marks_entry, name="teacher_marks_entry"),
    path("teacher/marks/", teacher_marks_list, name="teacher_marks_list"),
    # Staff/leadership dashboards
    path("rankings/class/", class_ranking_view, name="class_ranking"),
    path("rankings/school/", school_ranking_view, name="school_ranking"),
    path("admin/evaluations/", evaluation_admin, name="evaluation_admin"),
    path(
        "admin/evaluations/evidence/",
        evaluation_evidence_upload,
        name="evaluation_evidence_upload",
    ),
    path("grade-approvals/", grade_approval_list, name="grade_approval_list"),
    path(
        "grade-approvals/<uuid:request_id>/",
        grade_approval_detail,
        name="grade_approval_detail",
    ),
    path("grade-import/upload/", grade_import_upload_view, name="grade_import_upload"),
    path(
        "grade-import-template/",
        grade_import_template_view,
        name="grade_import_template",
    ),
    # PHASE 2: Compliance & Advanced Import
    path(
        "compliance/dashboard/", compliance_dashboard_view, name="compliance_dashboard"
    ),
    path(
        "compliance/deadline/<int:subject_assignment_id>/extend/",
        extend_deadline_view,
        name="extend_deadline",
    ),
    path(
        "api/grade-import/preview/",
        grade_import_preview_api,
        name="grade_import_preview_api",
    ),
    path(
        "api/grade-import/apply/", grade_import_apply_api, name="grade_import_apply_api"
    ),
    path(
        "api/rosetta/preview/",
        rosetta_grade_preview_api,
        name="rosetta_grade_preview_api",
    ),
    path("audit-trail/<int:evaluation_id>/", audit_trail_view, name="audit_trail"),
    path(
        "offline-conflict/<int:offline_entry_id>/resolve/",
        resolve_offline_conflict_view,
        name="resolve_offline_conflict",
    ),
    # PHASE 4: Import Monitoring & Caching
    path("import-jobs/monitor/", import_job_monitor_view, name="import_job_monitor"),
]
