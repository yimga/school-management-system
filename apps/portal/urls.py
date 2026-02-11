from django.urls import path

from .views import (
    badge_verify,
    parent_dashboard,
    parent_workflow_center,
    parent_medal_case,
    unified_calendar,
    my_digital_id,
    child_digital_id,
    parent_child_results,
    parent_attendance_discipline,
    portal_feature_page,
    portal_stats,
    parent_finance,
    link_child,
    link_child_wizard,
    claim_invite,
    teacher_dashboard_alias,
    teacher_workflow_alias,
    teacher_attendance_view,
    teacher_pay_history,
    teacher_leave,
    teacher_attendance_export,
    teacher_timetable,
    teacher_lesson_notes,
    teacher_hr_status,
    teacher_disciplinary,
    teacher_training_log,
    discipline_incidents_list,
    student_portal_grades,
    admissions_application_status,
    portal_syllabus,
    preview_student_syllabus,
    preview_communication_test,
    teacher_onboarding_wizard,
    student_onboarding_wizard,
)
from .views_support import support_request
from .views_contact_requests import (
    parent_contact_school,
    staff_contact_request_list,
    staff_contact_request_detail,
)
try:
    from .views_documents import (
        document_library_manage,
        document_upload,
        document_delete,
        document_download,
        document_download_pdf,
        signature_requests_manage,
        signature_request_create,
        signature_pending_list,
        signature_sign,
    )
    DOCUMENTS_AVAILABLE = True
except ImportError:
    DOCUMENTS_AVAILABLE = False
    document_library_manage = document_upload = document_delete = document_download = document_download_pdf = None
    signature_requests_manage = signature_request_create = signature_pending_list = signature_sign = None

app_name = "portal"

urlpatterns = [
    # Home and portal entry
    path("", parent_dashboard, name="home"),
    path("home/", parent_dashboard, name="portal_home"),
    
    # Parent portal
    path("parent/", parent_dashboard, name="parent_dashboard"),
    path("parent/workflow/", parent_workflow_center, name="parent_workflow"),
    path("parent/results/<int:student_id>/", parent_child_results, name="parent_child_results"),
    path("parent/link-child/", link_child_wizard, name="link_child"),  # New wizard as default
    path("parent/link-child/legacy/", link_child, name="link_child_legacy"),  # Keep old view for compatibility
    path("parent/claim-invite/", claim_invite, name="claim_invite"),
    path("parent/claim-invite/<str:token>/", claim_invite, name="claim_invite_token"),
    path("parent/finance/", parent_finance, name="parent_finance"),
    path("parent/contact-school/", parent_contact_school, name="parent_contact_school"),
    path("parent/medal-case/", parent_medal_case, name="parent_medal_case"),
    path("parent/child/<int:student_id>/id/", child_digital_id, name="child_digital_id"),
    path("teacher/my-id/", my_digital_id, name="my_digital_id"),
    path("badge/verify/", badge_verify, name="badge_verify"),
    path("support/", support_request, name="support_request"),
    # Backwards compatibility: older templates and tests expect 'parent_performance'
    path("parent/performance/", parent_child_results, name="parent_performance"),
    path("features/<str:feature>/", portal_feature_page, name="portal_feature"),
    path("parent/stats/", portal_stats, name="portal_stats"),
    path("syllabus/", portal_syllabus, name="portal_syllabus"),
    path("calendar/", unified_calendar, name="unified_calendar"),
    path("preview/syllabus/", preview_student_syllabus, name="preview_syllabus"),
    path("preview/communication/", preview_communication_test, name="preview_communication_test"),
    
    # Teacher dashboard
    path("teacher/", teacher_dashboard_alias, name="teacher_dashboard_alias"),
    path("teacher/workflow/", teacher_workflow_alias, name="teacher_workflow"),
    path("teacher/onboarding/", teacher_onboarding_wizard, name="teacher_onboarding"),
    path("teacher/attendance/", teacher_attendance_view, name="teacher_attendance"),
    path("teacher/attendance/export/", teacher_attendance_export, name="teacher_attendance_export"),
    path("teacher/pay-history/", teacher_pay_history, name="teacher_pay_history"),
    path("teacher/leave/", teacher_leave, name="teacher_leave"),
    path("teacher/timetable/", teacher_timetable, name="teacher_timetable"),
    path("teacher/lesson-notes/", teacher_lesson_notes, name="teacher_lesson_notes"),
    path("teacher/hr-status/", teacher_hr_status, name="teacher_hr_status"),
    path("teacher/disciplinary/", teacher_disciplinary, name="teacher_disciplinary"),
    path("teacher/training-log/", teacher_training_log, name="teacher_training_log"),
    path("parent/attendance-discipline/", parent_attendance_discipline, name="parent_attendance_discipline"),
    
    # Student onboarding
    path("student/onboarding/", student_onboarding_wizard, name="student_onboarding"),
    
    # Semantic aliases for Phase 7 URL cleanup
    path("student-portal/grades/", student_portal_grades, name="student_portal_grades"),
    path("admissions/application-status/", admissions_application_status, name="admissions_application_status"),

    # Staff triage: parent contact requests
    path("staff/contact-requests/", staff_contact_request_list, name="staff_contact_request_list"),
    path("staff/discipline/incidents/", discipline_incidents_list, name="discipline_incidents_list"),
    path("staff/contact-requests/<uuid:request_id>/", staff_contact_request_detail, name="staff_contact_request_detail"),
    
    # Document Library Management (Backend UI)
    path("backend/documents/", document_library_manage, name="document_library_manage"),
    path("backend/documents/upload/", document_upload, name="document_upload"),
    path("backend/documents/upload/<int:document_id>/", document_upload, name="document_edit"),
    path("backend/documents/delete/<int:document_id>/", document_delete, name="document_delete"),
    path("backend/documents/download/<int:document_id>/", document_download, name="document_download"),
    path("backend/documents/download/<int:document_id>/pdf/", document_download_pdf, name="document_download_pdf"),
    
    # Signature Requests Management
    path("backend/signatures/", signature_requests_manage, name="signature_requests_manage"),
    path("backend/signatures/create/", signature_request_create, name="signature_request_create"),
    
    # Parent Signature Interface
    path("parent/signatures/", signature_pending_list, name="signature_pending_list"),
    path("parent/signatures/sign/<int:signature_id>/", signature_sign, name="signature_sign"),
]
