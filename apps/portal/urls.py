from django.urls import path

from . import views_ai_surfaces as _ai_surfaces
from . import views_forums

from .views import (
    badge_verify,
    parent_dashboard,
    parent_settings_security,
    parent_set_active_child,
    parent_workflow_center,
    parent_medal_case,
    unified_calendar,
    my_digital_id,
    child_digital_id,
    parent_child_results,
    parent_attendance_discipline,
    portal_feature_page,
    portal_stats,
    teacher_feed,
    link_child,
    link_child_wizard,
    claim_invite,
    teacher_dashboard_alias,
    teacher_workflow_alias,
    teacher_attendance_view,
    take_student_attendance,
    record_teacher_attendance,
    seating_chart_view,
    teacher_pay_history,
    teacher_leave,
    teacher_attendance_export,
    teacher_timetable,
    teacher_lesson_notes,
    teacher_lesson_plan_add_attachment,
    teacher_wellness,
    teacher_hr_status,
    teacher_disciplinary,
    teacher_training_log,
    discipline_incidents_list,
    cahier_list,
    cahier_verify_list,
    cahier_visa,
    cahier_request_revisions,
    student_portal_grades,
    student_workflow_center,
    admissions_application_status,
    portal_syllabus,
    preview_student_syllabus,
    preview_communication_test,
)
from .parent_finance_health import parent_finance_health
from .views_parent_finance import (
    parent_feed,
    parent_finance,
    parent_finance_pay_all,
    parent_wallet,
)
from .views_attendance_export import (
    student_attendance_export,
    student_attendance_export_csv,
)
from .views_bulk_capture import teacher_bulk_capture_hub
from .views_onboarding import teacher_onboarding_wizard, student_onboarding_wizard
from .views_support import (
    support_help_hub,
    support_request,
    support_ticket_detail,
)
from .views_offline_sync import (
    api_offline_apply_batch,
    api_offline_enqueue,
    api_offline_process,
    offline_sync_conflicts,
    offline_sync_queue,
)
from .views_contact_requests import (
    parent_contact_school,
    staff_contact_request_list,
    staff_contact_request_detail,
)
from .views_photo_upload import (
    photo_upload_generate,
    photo_upload_generate_for_profile,
    photo_upload_phone_page,
    photo_upload_upload,
    photo_upload_status,
    photo_upload_qr,
    photo_upload_send_link_page,
)
from apps.people.employer_views import (
    employer_confirm_hours,
    employer_dashboard,
    employer_student_transcript,
)
from apps.student360.views import (
    student_360_page,
    student_360_export,
    transcript_archive,
    transcript_archive_year,
    transcript_freeze,
)
from .views_passport import (
    student_passport_detail,
    student_transcript_vault,
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
    document_library_manage = document_upload = document_delete = document_download = (
        document_download_pdf
    ) = None
    signature_requests_manage = signature_request_create = signature_pending_list = (
        signature_sign
    ) = None

from .views_ai_draft import (
    ai_draft_lesson_outline,
    ai_draft_parent_message,
    ai_draft_report_card_comment,
)
from .views_education_pack import education_pack_parent, education_pack_teacher
from .views_partner_docs import partner_documentation_assistant
from .views_runmycampus_guide import runmycampus_guide
# v4.00.9: streaming AI gateway view for the rmcStreamMount progressive client.
from .views_ai_stream import ai_stream_view
from .views_ai_line_admin import (
    tenant_ai_line_intents_view,
    tenant_ai_line_intents_save,
    ai_line_intent_coverage,
)

app_name = "portal"

urlpatterns = [
    # v4.00.9: streaming AI gateway — SSE chunks for rmcStreamMount.
    path("ai/stream/", ai_stream_view, name="ai_stream"),
    # v4.00.34: AI-line intent shortcuts editor + staff coverage dashboard.
    path("configure/ai-line-intents/", tenant_ai_line_intents_view, name="ai_line_intents"),
    path("configure/ai-line-intents/save/", tenant_ai_line_intents_save, name="ai_line_intents_save"),
    path("super/ai-line/intent-coverage/", ai_line_intent_coverage, name="ai_line_intent_coverage"),
    # Pass 13.D: AI draft endpoints (teacher-comms inbox + report-card editor).
    path("ai/draft/parent-message/", ai_draft_parent_message, name="ai_draft_parent_message"),
    path("ai/draft/report-card-comment/", ai_draft_report_card_comment, name="ai_draft_report_card_comment"),
    path("ai/draft/lesson-outline/", ai_draft_lesson_outline, name="ai_draft_lesson_outline"),
    path("guide/", runmycampus_guide, name="runmycampus_guide"),
    path("education/teacher/", education_pack_teacher, name="education_pack_teacher"),
    path("education/parent/", education_pack_parent, name="education_pack_parent"),
    path(
        "partner-docs/assistant/",
        partner_documentation_assistant,
        name="partner_documentation_assistant",
    ),
    # Home and portal entry
    path("", parent_dashboard, name="home"),
    path("home/", parent_dashboard, name="portal_home"),
    # Parent portal
    path("parent/", parent_dashboard, name="parent_dashboard"),
    path("parent/workflow/", parent_workflow_center, name="parent_workflow"),
    path(
        "parent/results/<int:student_id>/",
        parent_child_results,
        name="parent_child_results",
    ),
    path(
        "parent/link-child/", link_child_wizard, name="link_child"
    ),  # New wizard as default
    path(
        "parent/link-child/legacy/", link_child, name="link_child_legacy"
    ),  # Keep old view for compatibility
    path(
        "parent/set-active-child/<int:child_id>/",
        parent_set_active_child,
        name="parent_set_active_child",
    ),
    path("parent/claim-invite/", claim_invite, name="claim_invite"),
    path("parent/claim-invite/<str:token>/", claim_invite, name="claim_invite_token"),
    path("parent/finance/", parent_finance, name="parent_finance"),
    path(
        "parent/finance/health/",
        parent_finance_health,
        name="parent_finance_health",
    ),
    path(
        "parent/finance/pay-all/",
        parent_finance_pay_all,
        name="parent_finance_pay_all",
    ),
    path("parent/wallet/", parent_wallet, name="parent_wallet"),
    path(
        "parent/settings/security/",
        parent_settings_security,
        name="parent_settings_security",
    ),
    path("parent/feed/", parent_feed, name="parent_feed"),
    path("teacher/feed/", teacher_feed, name="teacher_feed"),
    path("parent/contact-school/", parent_contact_school, name="parent_contact_school"),
    path("parent/medal-case/", parent_medal_case, name="parent_medal_case"),  # rbac-allow: inline-auth (login redirect inside view)
    path(
        "parent/child/<int:student_id>/id/", child_digital_id, name="child_digital_id"
    ),
    path("teacher/my-id/", my_digital_id, name="my_digital_id"),
    path("badge/verify/", badge_verify, name="badge_verify"),  # rbac-allow: public badge-verifier — anyone with the badge URL can verify authenticity
    path("support/hub/", support_help_hub, name="support_help_hub"),
    path(
        "support/ticket/<uuid:ticket_id>/",
        support_ticket_detail,
        name="support_ticket_detail",
    ),
    path("support/", support_request, name="support_request"),
    path("offline/sync-queue/", offline_sync_queue, name="offline_sync_queue"),
    path("offline/conflicts/", offline_sync_conflicts, name="offline_sync_conflicts"),
    path("api/offline/enqueue/", api_offline_enqueue, name="api_offline_enqueue"),
    path("api/offline/process/", api_offline_process, name="api_offline_process"),
    path("api/offline/apply-batch/", api_offline_apply_batch, name="api_offline_apply_batch"),
    # Backwards compatibility: older templates and tests expect 'parent_performance'
    path("parent/performance/", parent_child_results, name="parent_performance"),
    path("forums/", views_forums.forum_home, name="forum_home"),
    path("forums/new/", views_forums.forum_new_topic, name="forum_new_topic"),
    path(
        "forums/category/<slug:category_slug>/",
        views_forums.forum_category,
        name="forum_category",
    ),
    path("forums/topic/<int:topic_id>/", views_forums.forum_topic, name="forum_topic"),
    path("features/<str:feature>/", portal_feature_page, name="portal_feature"),
    path("parent/stats/", portal_stats, name="portal_stats"),
    path("syllabus/", portal_syllabus, name="portal_syllabus"),
    path("calendar/", unified_calendar, name="unified_calendar"),
    path("preview/syllabus/", preview_student_syllabus, name="preview_syllabus"),
    path(
        "preview/communication/",
        preview_communication_test,
        name="preview_communication_test",
    ),
    # Teacher dashboard
    path("teacher/", teacher_dashboard_alias, name="teacher_dashboard_alias"),
    path("teacher/workflow/", teacher_workflow_alias, name="teacher_workflow"),
    path("teacher/onboarding/", teacher_onboarding_wizard, name="teacher_onboarding"),
    path(
        "teacher/bulk-capture/",
        teacher_bulk_capture_hub,
        name="teacher_bulk_capture_hub",
    ),
    path("teacher/attendance/", teacher_attendance_view, name="teacher_attendance"),
    path(
        "teacher/attendance/export/",
        teacher_attendance_export,
        name="teacher_attendance_export",
    ),
    path("teacher/pay-history/", teacher_pay_history, name="teacher_pay_history"),
    path("teacher/leave/", teacher_leave, name="teacher_leave"),
    path("teacher/timetable/", teacher_timetable, name="teacher_timetable"),
    path("teacher/lesson-notes/", teacher_lesson_notes, name="teacher_lesson_notes"),
    path(
        "teacher/lesson-notes/<int:lesson_plan_id>/add-resource/",
        teacher_lesson_plan_add_attachment,
        name="teacher_lesson_plan_add_attachment",
    ),
    path("teacher/wellness/", teacher_wellness, name="teacher_wellness"),
    path("teacher/hr-status/", teacher_hr_status, name="teacher_hr_status"),
    path("teacher/disciplinary/", teacher_disciplinary, name="teacher_disciplinary"),
    path("teacher/training-log/", teacher_training_log, name="teacher_training_log"),
    path(
        "parent/attendance-discipline/",
        parent_attendance_discipline,
        name="parent_attendance_discipline",
    ),
    # Student onboarding
    path("student/onboarding/", student_onboarding_wizard, name="student_onboarding"),
    path("student/workflow/", student_workflow_center, name="student_workflow"),
    # Semantic aliases for Phase 7 URL cleanup
    path("student-portal/grades/", student_portal_grades, name="student_portal_grades"),
    path(
        "admissions/application-status/",
        admissions_application_status,
        name="admissions_application_status",
    ),
    # Staff triage: parent contact requests
    path(
        "attendance/student/", take_student_attendance, name="take_student_attendance"
    ),
    path(
        "attendance/student/export/",
        student_attendance_export,
        name="student_attendance_export",
    ),
    path(
        "attendance/student/export/csv/",
        student_attendance_export_csv,
        name="student_attendance_export_csv",
    ),
    path(
        "attendance/teacher/",
        record_teacher_attendance,
        name="record_teacher_attendance",
    ),
    path("attendance/seating-chart/", seating_chart_view, name="seating_chart"),
    path(
        "staff/contact-requests/",
        staff_contact_request_list,
        name="staff_contact_request_list",
    ),
    path(
        "staff/discipline/incidents/",
        discipline_incidents_list,
        name="discipline_incidents_list",
    ),
    path("teacher/cahier/", cahier_list, name="cahier_list"),
    path("staff/cahier/verify/", cahier_verify_list, name="cahier_verify_list"),
    path("staff/cahier/visa/<int:entry_id>/", cahier_visa, name="cahier_visa"),
    path(
        "staff/cahier/revisions/<int:entry_id>/",
        cahier_request_revisions,
        name="cahier_request_revisions",
    ),
    path(
        "staff/contact-requests/<uuid:request_id>/",
        staff_contact_request_detail,
        name="staff_contact_request_detail",
    ),
    # Photo upload from another device
    path("photo-upload/generate/", photo_upload_generate, name="photo_upload_generate"),  # rbac-allow: inline-auth (login redirect inside view)
    path(
        "photo-upload/generate-for-profile/",
        photo_upload_generate_for_profile,
        name="photo_upload_generate_for_profile",
    ),
    path(  # rbac-allow: UUID token in URL is the auth (single-use phone upload link)
        "photo-upload/<uuid:token>/", photo_upload_phone_page, name="photo_upload_phone"
    ),
    path(  # rbac-allow: UUID token in URL is the auth (single-use phone upload link)
        "photo-upload/<uuid:token>/upload/",
        photo_upload_upload,
        name="photo_upload_upload",
    ),
    path(  # rbac-allow: UUID token in URL is the auth (single-use phone upload link)
        "photo-upload/<uuid:token>/status/",
        photo_upload_status,
        name="photo_upload_status",
    ),
    path("photo-upload/<uuid:token>/qr/", photo_upload_qr, name="photo_upload_qr"),  # rbac-allow: UUID token in URL is the auth (single-use phone upload link)
    path(
        "photo-upload/send-link/student/<int:student_id>/",
        photo_upload_send_link_page,
        name="photo_upload_send_link_student",
    ),
    path(
        "photo-upload/send-link/teacher/<int:teacher_id>/",
        photo_upload_send_link_page,
        name="photo_upload_send_link_teacher",
    ),
    # Document Library Management (Backend UI)
    path("backend/documents/", document_library_manage, name="document_library_manage"),
    path("backend/documents/upload/", document_upload, name="document_upload"),
    path(
        "backend/documents/upload/<int:document_id>/",
        document_upload,
        name="document_edit",
    ),
    path(
        "backend/documents/delete/<int:document_id>/",
        document_delete,
        name="document_delete",
    ),
    path(
        "backend/documents/download/<int:document_id>/",
        document_download,
        name="document_download",
    ),
    path(
        "backend/documents/download/<int:document_id>/pdf/",
        document_download_pdf,
        name="document_download_pdf",
    ),
    # Signature Requests Management
    path(
        "backend/signatures/",
        signature_requests_manage,
        name="signature_requests_manage",
    ),
    path(
        "backend/signatures/create/",
        signature_request_create,
        name="signature_request_create",
    ),
    # Parent Signature Interface
    path("parent/signatures/", signature_pending_list, name="signature_pending_list"),
    path(
        "parent/signatures/sign/<int:signature_id>/",
        signature_sign,
        name="signature_sign",
    ),
    # Student 360 (26.1) — full page + export; Section 15.1 immutable transcript + cross-year archive
    path("student/<int:student_id>/360/", student_360_page, name="student_360_page"),
    path(
        "student/<int:student_profile_id>/passport/",
        student_passport_detail,
        name="student_passport_detail",
    ),
    path(
        "student/<int:student_profile_id>/transcript-vault/",
        student_transcript_vault,
        name="student_transcript_vault",
    ),
    path(
        "student/<int:student_id>/360/export/",
        student_360_export,
        name="student_360_export",
    ),
    path(
        "student/<int:student_id>/360/transcript-archive/",
        transcript_archive,
        name="transcript_archive",
    ),
    path(
        "student/<int:student_id>/360/transcript-archive/<int:year_id>/",
        transcript_archive_year,
        name="transcript_archive_year",
    ),
    path(
        "student/<int:student_id>/360/transcript-freeze/",
        transcript_freeze,
        name="transcript_freeze",
    ),
    # Wave 6 (v2.98): AI surfaces — semantic search + risk drivers + grade outlook
    path(
        "students/search/",
        _ai_surfaces.semantic_student_search,
        name="ai_semantic_student_search",
    ),
    path(
        "student/<int:student_id>/risk-drivers/",
        _ai_surfaces.student_risk_drivers,
        name="ai_student_risk_drivers",
    ),
    path(
        "student/<int:student_id>/risk-drivers/regenerate/",
        _ai_surfaces.student_risk_explanation_regenerate,
        name="ai_student_risk_explanation_regenerate",
    ),
    path(
        "student/<int:student_id>/grade-outlook/",
        _ai_surfaces.student_grade_outlook,
        name="ai_student_grade_outlook",
    ),
    # Employer portal (apprentice hours verification + dual transcript)
    path("employer/", employer_dashboard, name="employer_dashboard"),
    path(
        "employer/<int:placement_id>/confirm/",
        employer_confirm_hours,
        name="employer_confirm_hours",
    ),
    path(
        "employer/<int:placement_id>/transcript/",
        employer_student_transcript,
        name="employer_student_transcript",
    ),
]
