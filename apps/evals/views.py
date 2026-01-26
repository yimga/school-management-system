from django.conf import settings
from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpRequest, HttpResponseForbidden, HttpResponse
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django import forms
import csv
import io
from decimal import Decimal
from typing import Any
from django.urls import reverse
from django.utils import timezone
from django.utils.safestring import mark_safe
import json

from apps.accounts.decorators import role_required, teacher_portal_required
from apps.accounts.models import User
from apps.academics.models import SubjectAssignment, Classroom, AcademicYear, Term, Subject
from apps.academics.services import get_active_year_and_term
from apps.people.models import TeacherProfile, StudentProfile
from apps.evals.models import GradeApprovalRequest, TeacherAssignment, Evaluation, AssessmentWeights
from apps.evals.importers import preview_import, apply_import, build_template_headers
from apps.reports.services import is_term_published
from apps.reports.weasy import render_pdf_bytes
from .forms import (
    BulkEvaluationCreateForm,
    EvaluationFilterForm,
    EvaluationEvidenceForm,
    AssessmentWeightsForm,
    BatchFillMissingForm,
    MarkSheetUploadForm,
    GradeApprovalDecisionForm,
)
from .models import EvaluationEvidence
from .ocr import process_marksheet_upload, is_tesseract_available
from .approval import (
    create_grade_approval_request,
    grade_entries_from_submission,
    grade_approver_roles,
    grade_post_roles,
    user_can_finalize_submission,
    FINAL_STATUSES,
)
from .notifications import NotificationService
from apps.portal.services import (
    teacher_dashboard_widget_data,
    teacher_scope,
    class_announcements_for_teacher,
    class_threads_for_teacher,
)
from apps.siteconfig.models import resolve_dashboard_widgets, SiteSettings, default_backend_feature_flags
from apps.siteconfig.models_dashboard import get_dashboard_widget_metadata
from apps.siteconfig.dashboard_views import load_dashboard_layout_settings
from apps.siteconfig.dashboard_views import _can_customize
from apps.finance.models import Notification


def _required_fields(academic_year, classroom, term):
    """Return Evaluation field names that should be considered required.

    Rule: any component with a configured weight > 0 is required.
    Fallback: seq1, seq2, exam.
    """
    weights = AssessmentWeights.get_for(
        academic_year=academic_year,
        classroom=classroom,
        term=term,
    )
    fields = []
    if weights.seq1_weight > 0:
        fields.append("seq1_score")
    if weights.seq2_weight > 0:
        fields.append("seq2_score")
    if weights.exam_weight > 0:
        fields.append("exam_score")
    if weights.mock_weight > 0:
        fields.append("mock_score")
    if weights.practical_weight > 0:
        fields.append("practical_score")

    return fields or ["seq1_score", "seq2_score", "exam_score"]


def _get_teacher_or_forbid(request: HttpRequest):
    teacher = TeacherProfile.objects.filter(user=request.user).first()
    if not teacher:
        return None, HttpResponseForbidden(
            "Teacher profile missing. Contact an administrator to finish setup."
        )
    return teacher, None


def _required_fields_for_evaluation(evaluation: Evaluation) -> list[str]:
    weights = AssessmentWeights.get_for(
        academic_year=evaluation.academic_year,
        classroom=evaluation.subject_assignment.classroom if evaluation.subject_assignment_id else None,
        term=evaluation.term,
    )
    fields = []
    if weights.seq1_weight > 0:
        fields.append("seq1_score")
    if weights.seq2_weight > 0:
        fields.append("seq2_score")
    if weights.exam_weight > 0:
        fields.append("exam_score")
    if weights.mock_weight > 0:
        fields.append("mock_score")
    if weights.practical_weight > 0:
        fields.append("practical_score")
    return fields or ["seq1_score", "seq2_score", "exam_score"]


def _serialize_evaluation(evaluation: Evaluation) -> dict[str, str]:
    sa = evaluation.subject_assignment
    student_name = f"{evaluation.student.last_name} {evaluation.student.first_name} ({evaluation.student.student_code})"
    return {
        "updated_at": evaluation.updated_at.strftime("%Y-%m-%d %H:%M"),
        "student": student_name,
        "classroom": sa.classroom.name if sa and sa.classroom else "",
        "subject": sa.subject.name if sa and sa.subject else "",
        "seq1": evaluation.seq1_score or evaluation.test1 or "",
        "seq2": evaluation.seq2_score or evaluation.test2 or "",
        "exam": evaluation.exam_score or "",
        "mock": evaluation.mock_score or "",
        "practical": evaluation.practical_score or "",
        "total": f"{evaluation.total_score:.2f}",
        "remarks": evaluation.remarks or "",
    }


def _update_evaluations_from_entries(entries, students_map, teacher, year, term, subject_assignment) -> int:
    updated = 0
    for entry in entries:
        student = students_map.get(entry["student_id"])
        if student is None:
            continue
        Evaluation.objects.update_or_create(
            academic_year=year,
            term=term,
            subject_assignment=subject_assignment,
            student=student,
            defaults={
                "teacher": teacher,
                "seq1_score": entry["scores"]["seq1"],
                "seq2_score": entry["scores"]["seq2"],
                "exam_score": entry["scores"]["exam"],
                "mock_score": entry["scores"]["mock"],
                "practical_score": entry["scores"]["practical"],
                "test1": entry["scores"]["seq1"],
                "test2": entry["scores"]["seq2"],
                "remarks": entry.get("remarks", ""),
            },
        )
        updated += 1
    return updated


def _user_can_review_grades(user: User) -> bool:
    if not user.is_authenticated:
        return False
    if getattr(user, "is_superuser", False):
        return True
    roles = grade_approver_roles()
    if user.role in roles:
        return True
    return user.roles.filter(code__in=roles).exists()


def _student_lookup_by_code(students: list[StudentProfile]) -> dict[str, StudentProfile]:
    return {
        (student.student_code or "").upper(): student
        for student in students
        if student.student_code
    }


def _apply_ocr_entries(entries, student_lookup, sa, year, term, teacher):
    updated = []
    for entry in entries:
        student = student_lookup.get(entry.get("student_code", "").upper())
        if not student:
            continue
        evaluation, _ = Evaluation.objects.get_or_create(
            academic_year=year,
            term=term,
            subject_assignment=sa,
            student=student,
            defaults={"teacher": teacher},
        )
        changes = {}
        for field, value in entry.get("scores", {}).items():
            if value is None:
                continue
            existing = getattr(evaluation, field)
            if existing != value:
                setattr(evaluation, field, value)
                changes[field] = value
        if changes:
            evaluation._audit_change_type = 'ocr_upload'
            evaluation.teacher = teacher
            evaluation.save()
            updated.append({"student": student, "changes": changes})
    return updated


def _build_ocr_preview(entries, student_lookup):
    preview = []
    for entry in entries:
        student = student_lookup.get(entry.get("student_code", "").upper())
        full_name = ""
        if student:
            full_name = f"{student.last_name} {student.first_name}"
        preview.append(
            {
                "code": entry.get("student_code"),
                "student_name": full_name if full_name else "Unmatched student",
                "scores": entry.get("scores", {}),
                "line": entry.get("line_text"),
                "matched": bool(student),
            }
        )
    return preview


MARKSHEET_OCR_PENDING_SESSION_KEY = "marksheet_ocr_pending"


def _serialize_pending_entries(entries):
    serialized = []
    for entry in entries:
        serialized.append(
            {
                "student_code": entry.get("student_code"),
                "line_text": entry.get("line_text"),
                "scores": {field: str(value) for field, value in entry.get("scores", {}).items()},
            }
        )
    return serialized


def _deserialize_pending_entries(payload):
    deserialized = []
    for entry in payload:
        scores = {}
        for field, value in entry.get("scores", {}).items():
            try:
                scores[field] = Decimal(str(value))
            except Exception:
                continue
        deserialized.append(
            {
                "student_code": entry.get("student_code"),
                "line_text": entry.get("line_text"),
                "scores": scores,
            }
        )
    return deserialized


def _pending_ocr_for(session, teacher_id, subject_assignment_id):
    pending = session.get(MARKSHEET_OCR_PENDING_SESSION_KEY)
    if not pending:
        return None
    if pending.get("teacher") != teacher_id:
        return None
    if pending.get("subject_assignment") != subject_assignment_id:
        return None
    return pending


def _set_pending_ocr(session, teacher_id, subject_assignment_id, entries, confidence):
    session[MARKSHEET_OCR_PENDING_SESSION_KEY] = {
        "teacher": teacher_id,
        "subject_assignment": subject_assignment_id,
        "entries": _serialize_pending_entries(entries),
        "confidence": confidence,
    }
    session.modified = True


def _clear_pending_ocr(session):
    if MARKSHEET_OCR_PENDING_SESSION_KEY in session:
        session.pop(MARKSHEET_OCR_PENDING_SESSION_KEY, None)
        session.modified = True


def _build_filter_labels(
    classroom_id: str | None,
    subject_id: str | None,
    term_id: str | None,
    missing_only: bool,
    classroom_map: dict[str, str],
    subject_map: dict[str, str],
) -> dict[str, str]:
    labels = {}
    if classroom_id:
        labels["Classroom"] = classroom_map.get(classroom_id, classroom_id)
    if subject_id:
        labels["Subject"] = subject_map.get(subject_id, subject_id)
    if term_id:
        term = Term.objects.filter(id=term_id).first()
        if term:
            labels["Term"] = term.label
    labels["Missing"] = "Yes" if missing_only else "All"
    return labels


@teacher_portal_required
@role_required(User.Role.TEACHER)
def teacher_dashboard(request: HttpRequest):
    teacher, error = _get_teacher_or_forbid(request)
    if error:
        return error
    year, term = get_active_year_and_term()
    if not year or not term:
        return HttpResponseForbidden("No active academic year/term set by admin yet.")

    teacher_profile, assignments, students_qs, classrooms = teacher_scope(request.user, academic_year=year)
    if teacher_profile is None:
        return error

    # Progress indicators per assignment (filled / total)
    progress = {}
    for a in assignments:
        sa = a.subject_assignment
        total = StudentProfile.objects.filter(
            academic_year=year,
            classroom=sa.classroom,
            specialty=sa.specialty,
            is_active=True,
        ).count()

        required = _required_fields(year, sa.classroom, term)
        # Count evaluations that have all required fields filled
        qs = Evaluation.objects.filter(
            academic_year=year,
            term=term,
            subject_assignment=sa,
        )
        for f in required:
            qs = qs.exclude(**{f"{f}__isnull": True})
        filled = qs.count()
        width_pct = round((filled / total) * 100, 0) if total else 0
        progress[a.id] = {"filled": filled, "total": total, "width": width_pct}

    widget_data = teacher_dashboard_widget_data(assignments, progress, year, term, teacher=teacher)
    attendance = widget_data.get("attendance") or {}
    attendance_pct = attendance.get("overall")
    hero_stats = [
        {"label": "Assignments", "value": widget_data["assignments_count"], "meta": "Active subjects"},
        {"label": "Completion", "value": f"{widget_data['completion_pct']}%", "progress": widget_data["completion_pct"], "meta": "Marks entered"},
        {"label": "Pending", "value": widget_data["tasks"]["pending_evaluations"], "meta": "Marks remaining"},
    ]
    if attendance_pct is not None:
        hero_stats.append({
            "label": "Attendance",
            "value": f"{attendance_pct}%",
            "meta": "Class average",
        })
    missing_records_url = f"{reverse('evals:evaluation_admin')}?missing=1"
    hero = {
        "tagline": "Teacher Dashboard",
        "title": "Your classes at a glance",
        "subtitle": f"{year.name} · {term.label}",
        "icon": "bi-easel",
        "stats": hero_stats,
        "actions": [
            {"label": "Enter marks", "url": reverse("evals:teacher_marks_entry")},
            {"label": "Finish missing records", "url": missing_records_url},
            {"label": "Grade import", "url": reverse("evals:grade_import_upload")},
            {"label": "Download template", "url": reverse("evals:grade_import_template")},
        ],
    }

    preference = getattr(request.user, "preferences", None)
    display_widgets = resolve_dashboard_widgets(getattr(request.user, "role", None), preference)
    class_announcements = class_announcements_for_teacher(
        request.user,
        classrooms,
        department_id=getattr(teacher_profile.department, "id", None),
        limit=6,
    )
    class_threads = class_threads_for_teacher(request.user, limit=6)

    peers = []
    if getattr(teacher_profile, "department", None):
        peer_qs = (
            TeacherProfile.objects.select_related("user")
            .filter(department=teacher_profile.department)
            .exclude(id=teacher_profile.id)[:6]
        )
        for peer in peer_qs:
            user = peer.user
            peers.append({
                "name": user.get_full_name() or user.username,
                "role": getattr(user, "role", ""),
            })

    flags = {**default_backend_feature_flags(), **(getattr(SiteSettings.get_solo(), "backend_feature_flags", {}) or {})}
    finance_banner = None
    if flags.get("require_guardian_finance_opt_in"):
        finance_banner = (
            "Parents need finance opt-in to view invoices. "
            f"Requests are {'enabled' if flags.get('allow_finance_access_requests', True) else 'disabled'}."
        )
    else:
        finance_banner = "Parent finance access is open (no opt-in required)."
    finance_summary = (
        f"{widget_data['finance']['total_due']} total due • {widget_data['finance']['paid']} paid"
        if widget_data["finance"].get("total_due")
        else "Finance metrics will appear once invoices are issued."
    )
    finance_access_banner = {
        "text": finance_banner,
        "summary": finance_summary,
        "level": "info",
        "request_url": None,
        "cta": None,
    }
    finance_requests_qs = Notification.objects.filter(
        recipient=request.user,
        title__icontains="finance access request",
    ).order_by("-created_at")
    finance_request_link = reverse("finance:requests")

    dashboard_settings = load_dashboard_layout_settings(request.user, "teacher")
    available_sidebar_items = [
        {"id": "teacher-home", "label": "Teacher hub", "url": reverse("portal:teacher_dashboard"), "icon": "bi-person-lines-fill"},
        {"id": "teacher-attendance", "label": "Attendance", "url": reverse("portal:teacher_attendance"), "icon": "bi-calendar-check"},
        {"id": "teacher-pay", "label": "Pay history", "url": reverse("portal:teacher_pay_history"), "icon": "bi-wallet2"},
        {"id": "teacher-syllabus", "label": "Syllabus", "url": reverse("portal:portal_syllabus"), "icon": "bi-journal-text"},
    ]
    dashboard_layout_url = reverse("api:dashboard-layout", kwargs={"page": "teacher"})
    allow_custom_layout = _can_customize(request.user)

    return render(request, "teacher/dashboard.html", {
        "year": year,
        "term": term,
        "assignments": assignments,
        "progress": progress,
        "widget_data": widget_data,
        "hero": hero,
        "missing_records_url": missing_records_url,
        "grade_import_upload_url": reverse("evals:grade_import_upload"),
        "grade_import_template_url": reverse("evals:grade_import_template"),
        "display_widgets": display_widgets,
        "class_announcements": class_announcements,
        "class_threads": class_threads,
        "team_peers": peers,
        "team_department": getattr(teacher_profile, "department", None),
        "finance_access_message": finance_banner,
        "finance_access_banner": finance_access_banner,
        "allow_custom_layout": allow_custom_layout,
        "dashboard_settings": dashboard_settings,
        "dashboard_layout_url": dashboard_layout_url,
        "available_sidebar_items": available_sidebar_items,
        "widget_meta_json": mark_safe(json.dumps(get_dashboard_widget_metadata())),
        "finance_requests_count": finance_requests_qs.count(),
        "finance_request_notifications": finance_requests_qs[:5],
        "finance_request_link": finance_request_link,
    })

@teacher_portal_required
@role_required(User.Role.TEACHER)
def teacher_marks_entry(request: HttpRequest):
    teacher, error = _get_teacher_or_forbid(request)
    if error:
        return error
    year, active_term = get_active_year_and_term()
    if not year or not active_term:
        return HttpResponseForbidden("No active academic year/term set by admin yet.")

    teacher_assignments = TeacherAssignment.objects.filter(
        teacher=teacher,
        academic_year=year,
        is_active=True
    ).select_related("subject_assignment")

    selected_sa_id = request.GET.get("subject_assignment_id") or request.POST.get("subject_assignment_id")
    sa = None
    students = []
    existing = {}  # student_id -> Evaluation
    locked = False

    show_missing = request.GET.get("missing") == "1"
    required_fields = []
    filled_count = 0
    total_students_count = 0
    site_settings = SiteSettings.get_solo()
    flags = {**default_backend_feature_flags(), **(site_settings.backend_feature_flags or {})}
    grade_approval_enabled = getattr(site_settings, "grade_approval_enabled", False)
    custom_cmd = (site_settings.marksheet_ocr_command or "").strip()
    env_cmd = getattr(settings, "MARKSHEET_OCR_COMMAND", "") or ""
    resolved_cmd = (custom_cmd or env_cmd or "").strip()
    ocr_command = resolved_cmd or None
    marksheet_ocr_ready, marksheet_ocr_version = is_tesseract_available(ocr_command)
    marksheet_ocr_command_display = resolved_cmd or "tesseract"
    upload_form = MarkSheetUploadForm(initial={"subject_assignment_id": selected_sa_id}) if selected_sa_id else MarkSheetUploadForm()
    upload_preview = []
    upload_feedback = None
    upload_summary: dict[str, Any] = {"processed": 0}
    upload_confidence = 0.0
    upload_manual_review_pending = False
    student_lookup: dict[str, StudentProfile] = {}

    if selected_sa_id:
        # Guard: must be assigned
        if not teacher_assignments.filter(subject_assignment_id=selected_sa_id).exists():
            return HttpResponseForbidden("You are not assigned to this subject/class.")

        sa = get_object_or_404(SubjectAssignment, id=selected_sa_id)
        if getattr(active_term, "position", None) == 3 and not sa.classroom.allows_third_term:
            return HttpResponseForbidden("Third term is not enabled for this classroom.")

        # Publish lock check
        locked = is_term_published(year.id, active_term.id, sa.classroom_id)

        # Load students for this class/specialty/year
        students = list(StudentProfile.objects.filter(
            academic_year=year,
            classroom=sa.classroom,
            specialty=sa.specialty,
            is_active=True
        ).order_by("last_name", "first_name"))

        total_students_count = len(students)

        required_fields = _required_fields(year, sa.classroom, active_term)

        # Load existing evaluations so we can pre-fill inputs
        evals = Evaluation.objects.filter(
            academic_year=year,
            term=active_term,
            subject_assignment=sa,
            student__in=students
        )
        existing = {e.student_id: e for e in evals}

        # Progress + optional filtering
        def _is_complete(e: Evaluation | None) -> bool:
            if not e:
                return False
            return all(getattr(e, f) is not None for f in required_fields)

        filled_count = sum(1 for s in students if _is_complete(existing.get(s.id)))

        if show_missing:
            students = [s for s in students if not _is_complete(existing.get(s.id))]

        student_lookup = _student_lookup_by_code(students)

    grade_approval_requests = GradeApprovalRequest.objects.none()
    if sa:
        grade_approval_requests = GradeApprovalRequest.objects.filter(
            teacher=teacher,
            subject_assignment=sa,
        ).order_by("-requested_at")[:3]
    marksheet_file = request.FILES.get("marksheet_file")
    confirm_pending = request.POST.get("confirm_pending") == "1"
    selected_sa_pk = sa.id if sa else None
    pending_data = _pending_ocr_for(request.session, teacher.id, selected_sa_pk) if selected_sa_pk else None

    if request.method == "POST" and confirm_pending:
        upload_form = MarkSheetUploadForm(initial={"subject_assignment_id": selected_sa_id}) if selected_sa_id else MarkSheetUploadForm()
        if not sa:
            messages.error(request, "Please select an assignment first.")
            upload_feedback = {"level": "danger", "message": "Select an assignment before uploading a marksheet."}
        elif locked:
            return HttpResponseForbidden("This term is published/locked. Marks entry is disabled.")
        elif not pending_data:
            upload_feedback = {
                "level": "warning",
                "message": "No OCR preview is staged for this assignment.",
            }
        else:
            entries = _deserialize_pending_entries(pending_data["entries"])
            upload_confidence = pending_data.get("confidence", 0.0) or 0.0
            upload_preview = _build_ocr_preview(entries, student_lookup)
            applied = _apply_ocr_entries(entries, student_lookup, sa, year, active_term, teacher)
            upload_summary = {
                "processed": len(entries),
                "confidence": upload_confidence,
                "applied": len(applied),
            }
            upload_feedback = {
                "level": "success" if applied else "info",
                "message": (
                    f"Applied {len(applied)} parsed entries at {upload_confidence:.0f}% confidence."
                    if applied
                    else "No matching students were updated."
                ),
            }
            messages.success(request, "OCR preview applied successfully.")
            _clear_pending_ocr(request.session)
    elif request.method == "POST" and marksheet_file:
        upload_form = MarkSheetUploadForm(request.POST, request.FILES)
        if not sa:
            messages.error(request, "Please select an assignment first.")
            upload_feedback = {"level": "danger", "message": "Select an assignment before uploading a marksheet."}
        elif locked:
            return HttpResponseForbidden("This term is published/locked. Marks entry is disabled.")
        elif not upload_form.is_valid():
            upload_feedback = {"level": "danger", "message": "Upload form is invalid. Check the fields and try again."}
        elif not flags.get("marksheet_ocr_enabled"):
            upload_feedback = {
                "level": "warning",
                "message": "Marksheet OCR uploads are disabled in Site Settings.",
            }
        elif not marksheet_ocr_ready:
            upload_feedback = {
                "level": "warning",
                "message": (
                    "Tesseract is not available. Please install it or configure the path in Site Settings."
                ),
            }
        else:
            ocr_result = process_marksheet_upload(
                upload_form.cleaned_data["marksheet_file"],
                tesseract_cmd=ocr_command,
            )
            entries = ocr_result.get("entries", [])
            upload_confidence = ocr_result.get("confidence", 0.0) or 0.0
            upload_preview = _build_ocr_preview(entries, student_lookup)
            threshold = flags.get("marksheet_ocr_confidence_threshold", 70) or 70
            upload_manual_review_pending = bool(flags.get("marksheet_ocr_manual_review_required", True)) or upload_confidence < threshold
            upload_summary = {
                "processed": len(entries),
                "confidence": upload_confidence,
            }
            if entries and not upload_manual_review_pending:
                applied = _apply_ocr_entries(entries, student_lookup, sa, year, active_term, teacher)
                upload_summary["applied"] = len(applied)
                upload_feedback = {
                    "level": "success",
                    "message": f"Applied {len(applied)} parsed entries at {upload_confidence:.0f}% confidence.",
                }
                messages.success(request, "OCR upload applied successfully.")
                _clear_pending_ocr(request.session)
            elif entries:
                upload_feedback = {
                    "level": "info",
                    "message": "Parsed marks need manual verification before they are applied.",
                }
                _set_pending_ocr(request.session, teacher.id, selected_sa_pk, entries, upload_confidence)
            else:
                upload_feedback = {
                    "level": "warning",
                    "message": ocr_result.get("message") or "No data extracted from the marksheet.",
                }
                _clear_pending_ocr(request.session)
    elif request.method == "POST":
        if not sa:
            messages.error(request, "Please select an assignment first.")
            return redirect("evals:teacher_marks_entry")

        if locked:
            return HttpResponseForbidden("This term is published/locked. Marks entry is disabled.")

        action = request.POST.get("action")
        entries_payload = grade_entries_from_submission(students, request.POST)
        students_map = {student.id: student for student in students}
        _update_evaluations_from_entries(
            entries_payload,
            students_map,
            teacher,
            year,
            active_term,
            sa,
        )

        if action == "submit_for_approval" and grade_approval_enabled:
            try:
                create_grade_approval_request(
                    teacher=teacher,
                    subject_assignment=sa,
                    academic_year=year,
                    term=active_term,
                    entries=entries_payload,
                    requested_by=request.user,
                )
            except ValueError:
                messages.warning(request, "Enter at least one mark before requesting approval.")
            else:
                messages.success(request, "Grades submitted for review. Awaiting approver feedback.")
                return redirect("evals:teacher_marks_list")

        messages.success(request, "Marks saved successfully.")
        return redirect("evals:teacher_marks_list")

    pending_data = _pending_ocr_for(request.session, teacher.id, selected_sa_pk) if selected_sa_pk else None
    if pending_data:
        pending_entries = _deserialize_pending_entries(pending_data["entries"])
        upload_preview = _build_ocr_preview(pending_entries, student_lookup)
        upload_confidence = pending_data.get("confidence", upload_confidence) or 0.0
        upload_summary = {
            "processed": len(pending_entries),
            "confidence": upload_confidence,
        }
        upload_manual_review_pending = True

    # GET: render selection + (optional) student table
    return render(request, "teacher/marks_entry.html", {
        "year": year,
        "term": active_term,
        "teacher_assignments": teacher_assignments,
        "selected_sa_id": str(selected_sa_id) if selected_sa_id else "",
        "sa": sa,
        "selected_sa": sa,
        "students": students,
        "existing": existing,
        "locked": locked,
        "show_missing": show_missing,
        "required_fields": required_fields,
        "filled_count": filled_count,
        "total_students": total_students_count if selected_sa_id else 0,
        "upload_form": upload_form,
        "upload_preview": upload_preview,
        "upload_feedback": upload_feedback,
        "upload_summary": upload_summary,
        "upload_confidence": upload_confidence,
        "upload_manual_review_pending": upload_manual_review_pending,
        "marksheet_ocr_enabled": flags.get("marksheet_ocr_enabled"),
        "marksheet_mobile_upload_allowed": flags.get("marksheet_ocr_mobile_upload_enabled", True),
        "marksheet_ocr_ready": marksheet_ocr_ready,
        "marksheet_ocr_version": marksheet_ocr_version,
        "marksheet_ocr_command": marksheet_ocr_command_display,
        "grade_approval_enabled": grade_approval_enabled,
        "grade_approval_requests": grade_approval_requests,
        "grade_approval_roles": grade_approver_roles(),
    })

@teacher_portal_required
@role_required(User.Role.TEACHER)
def teacher_marks_list(request: HttpRequest):
    teacher, error = _get_teacher_or_forbid(request)
    if error:
        return error
    user_name = request.user.get_full_name() or request.user.username
    year, term = get_active_year_and_term()
    if not year or not term:
        return HttpResponseForbidden("No active academic year/term set by admin yet.")

    classroom_id = request.GET.get("classroom")
    subject_id = request.GET.get("subject")
    term_id = request.GET.get("term")
    missing_only = request.GET.get("missing") == "1"
    export_csv = request.GET.get("export") == "csv"
    export_pdf = request.GET.get("export") == "pdf"

    teacher_assignments = TeacherAssignment.objects.filter(
        teacher=teacher,
        academic_year=year,
        is_active=True
    )

    classrooms = (
        teacher_assignments.values_list("subject_assignment__classroom_id", "subject_assignment__classroom__name")
        .distinct()
    )
    subjects = (
        teacher_assignments.values_list("subject_assignment__subject_id", "subject_assignment__subject__name")
        .distinct()
    )
    classroom_map = {str(item[0]): item[1] for item in classrooms if item[0]}
    subject_map = {str(item[0]): item[1] for item in subjects if item[0]}

    qs = Evaluation.objects.filter(teacher=teacher, academic_year=year)
    if classroom_id:
        qs = qs.filter(subject_assignment__classroom_id=classroom_id)
    if subject_id:
        qs = qs.filter(subject_assignment__subject_id=subject_id)
    if term_id:
        qs = qs.filter(term_id=term_id)

    # PERFORMANCE FIX: Apply missing_only filter at database level to avoid loading all records into memory
    if missing_only:
        # Filter for records where any required score field is NULL
        from django.db.models import Q
        qs = qs.filter(
            Q(seq1_score__isnull=True) | Q(test1__isnull=True) |
            Q(seq2_score__isnull=True) | Q(test2__isnull=True) |
            Q(exam_score__isnull=True) | Q(mock_score__isnull=True) |
            Q(practical_score__isnull=True)
        )

    evals = qs.select_related(
        "student",
        "term",
        "subject_assignment__subject",
        "subject_assignment__classroom",
        "subject_assignment__specialty",
    ).order_by("-updated_at")

    # PERFORMANCE FIX: Add pagination to prevent memory exhaustion with 15,000+ records
    from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
    page_number = request.GET.get('page', 1)
    paginator = Paginator(evals, 50)  # 50 records per page
    
    try:
        evals_page = paginator.page(page_number)
    except PageNotAnInteger:
        evals_page = paginator.page(1)
    except EmptyPage:
        evals_page = paginator.page(paginator.num_pages)
    
    evals_list = list(evals_page)

    if export_pdf:
        rows = [_serialize_evaluation(e) for e in evals_list]
        filters = _build_filter_labels(classroom_id, subject_id, term_id, missing_only, classroom_map, subject_map)
        pdf_context = {
            "report_title": f"{user_name} Marks Export",
            "report_period": f"{term.label} · {year.name}",
            "report_total": f"{len(rows)} records",
            "rows": rows,
            "filters": filters,
            "generated_at": timezone.now(),
            "summary": f"{len(rows)} evaluations",
        }
        pdf_bytes = render_pdf_bytes(request, "reports/evaluation_grid.html", pdf_context)
        filename = f"teacher-marks-{year.name}-{term.name}.pdf".replace(" ", "_")
        response = HttpResponse(pdf_bytes, content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response

    if export_csv:
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="teacher-marks.csv"'
        writer = csv.writer(response)
        writer.writerow([
            "Updated",
            "Student",
            "Class",
            "Subject",
            "Term",
            "Seq1/Test1",
            "Seq2/Test2",
            "Exam",
            "Mock",
            "Practical",
            "Remarks",
        ])
        for e in evals_list:
            writer.writerow([
                e.updated_at,
                f"{e.student.last_name} {e.student.first_name} ({e.student.student_code})",
                e.subject_assignment.classroom.name if e.subject_assignment else "",
                e.subject_assignment.subject.name if e.subject_assignment else "",
                e.term.label,
                e.seq1_score or e.test1,
                e.seq2_score or e.test2,
                e.exam_score,
                e.mock_score,
                e.practical_score,
                e.remarks,
            ])
        return response

    export_csv_params = request.GET.copy()
    export_csv_params["export"] = "csv"
    export_pdf_params = request.GET.copy()
    export_pdf_params["export"] = "pdf"

    return render(request, "teacher/marks_list.html", {
        "year": year,
        "term": term,
        "evals": evals_list,
        "paginator": paginator,
        "page_obj": evals_page,
        "classrooms": list(classrooms),
        "subjects": list(subjects),
        "term_choices": list(Term.objects.all()),
        "selected": {
            "classroom": classroom_id or "",
            "subject": subject_id or "",
            "term": term_id or "",
            "missing": "1" if missing_only else "",
        },
        "export_csv_query": export_csv_params.urlencode(),
        "export_pdf_query": export_pdf_params.urlencode(),
    })


@staff_member_required
def class_ranking_view(request: HttpRequest):
    """Class ranking (best to worst) for a given year/term/classroom.

    This is a staff-only view intended for Admin/Leadership.

    Optimization: Uses cached rankings with 15-minute TTL and batch-loaded
    evaluations to avoid N+1 queries.
    """
    year, active_term = get_active_year_and_term()
    if not year or not active_term:
        return HttpResponseForbidden("No active academic year/term set by admin yet.")

    year_id = request.GET.get("year") or str(year.id)
    term_id = request.GET.get("term") or str(active_term.id)
    classroom_id = request.GET.get("classroom")

    year_obj = get_object_or_404(AcademicYear, id=year_id)
    term_obj = get_object_or_404(Term, id=term_id)

    classrooms = Classroom.objects.filter(academic_year=year_obj).order_by("name")
    selected_classroom = None
    ranking = []
    stats = None
    rows = []

    if classroom_id:
        selected_classroom = get_object_or_404(Classroom, id=classroom_id)

        from .services import get_class_stats
        from .ranking import get_class_ranking

        # Get optimized ranking with tie handling and caching
        ranking = get_class_ranking(selected_classroom, term_obj)
        stats = get_class_stats(selected_classroom, year_obj, term_obj)

        # Build rows from ranking entries (rank already included)
        rows = [
            {
                "rank": entry.rank,
                "student": entry.student,
                "average": entry.average,
                "is_tied": entry.is_tied,
                "tied_count": entry.tied_count,
                "percentile": entry.percentile,
            }
            for entry in ranking
        ]

    return render(request, "evals/class_ranking.html", {
        "year": year_obj,
        "term": term_obj,
        "selected_year": year_obj,
        "selected_term": term_obj,
        "years": AcademicYear.objects.order_by("-start_date"),
        "terms": Term.objects.filter(academic_year=year_obj).order_by("start_date", "name"),
        "classrooms": classrooms,
        "selected_classroom": selected_classroom,
        "rows": rows,
        "stats": stats,
    })


@staff_member_required
def school_ranking_view(request: HttpRequest):
    """School-wide ranking for a given year/term.

    Optimization: Uses cached rankings with 15-minute TTL and batch-loaded
    evaluations to avoid N+1 queries. Proper tie handling ensures deterministic
    ranking even when students have identical averages.
    """
    year, active_term = get_active_year_and_term()
    if not year or not active_term:
        return HttpResponseForbidden("No active academic year/term set by admin yet.")

    year_id = request.GET.get("year") or str(year.id)
    term_id = request.GET.get("term") or str(active_term.id)

    year_obj = get_object_or_404(AcademicYear, id=year_id)
    term_obj = get_object_or_404(Term, id=term_id)

    from .ranking import get_school_ranking

    # Get optimized ranking with tie handling and caching
    ranking = get_school_ranking(term_obj)

    # Build rows from ranking entries (rank already included with tie handling)
    rows = [
        {
            "rank": entry.rank,
            "student": entry.student,
            "average": entry.average,
            "is_tied": entry.is_tied,
            "tied_count": entry.tied_count,
            "percentile": entry.percentile,
        }
        for entry in ranking
    ]

    return render(request, "evals/school_ranking.html", {
        "year": year_obj,
        "term": term_obj,
        "selected_year": year_obj,
        "selected_term": term_obj,
        "years": AcademicYear.objects.order_by("-start_date"),
        "terms": Term.objects.filter(academic_year=year_obj).order_by("start_date", "name"),
        "rows": rows,
    })


@staff_member_required
def evaluation_admin(request: HttpRequest):
    year, active_term = get_active_year_and_term()
    if not year or not active_term:
        return HttpResponseForbidden("No active academic year/term set by admin yet.")

    year_id = request.GET.get("year") or str(year.id)
    term_id = request.GET.get("term") or str(active_term.id)
    classroom_id = request.GET.get("classroom")
    subject_id = request.GET.get("subject")
    missing_only = request.GET.get("missing") == "1"

    year_obj = get_object_or_404(AcademicYear, id=year_id)
    term_obj = get_object_or_404(Term, id=term_id)
    classroom_obj = Classroom.objects.filter(id=classroom_id).first() if classroom_id else None

    filter_form = EvaluationFilterForm(
        data=request.GET or None,
        academic_year=year_obj,
    )

    current_weights = AssessmentWeights.get_for(
        academic_year=year_obj,
        classroom=classroom_obj,
        term=term_obj,
    )
    weights_initial = {
        "academic_year": current_weights.academic_year,
        "term": current_weights.term,
        "classroom": current_weights.classroom,
        "seq1_weight": current_weights.seq1_weight,
        "seq2_weight": current_weights.seq2_weight,
        "exam_weight": current_weights.exam_weight,
        "mock_weight": current_weights.mock_weight,
        "practical_weight": current_weights.practical_weight,
        "score_scale": current_weights.score_scale,
    }

    create_form = BulkEvaluationCreateForm(
        data=request.POST or None,
        academic_year=year_obj,
        term=term_obj,
        prefix="create",
    )
    weights_form = AssessmentWeightsForm(
        data=request.POST or None,
        academic_year=year_obj,
        prefix="weights",
        initial=weights_initial if request.method != "POST" else None,
    )
    fill_form = BatchFillMissingForm(
        data=request.POST or None,
        prefix="fill",
    )

    if request.method == "POST" and request.POST.get("action") == "bulk_create":
        if create_form.is_valid():
            subject_assignment = create_form.cleaned_data["subject_assignment"]
            teacher = create_form.cleaned_data["teacher"]

            students = StudentProfile.objects.filter(
                academic_year=year_obj,
                classroom=subject_assignment.classroom,
                specialty=subject_assignment.specialty,
                is_active=True,
            )

            created = 0
            for student in students:
                _, was_created = Evaluation.objects.get_or_create(
                    academic_year=year_obj,
                    term=subject_assignment.term,
                    subject_assignment=subject_assignment,
                    student=student,
                    defaults={"teacher": teacher},
                )
                if was_created:
                    created += 1

            messages.success(
                request,
                f"Created {created} evaluations for {subject_assignment}.",
            )
            return redirect(request.path + f"?year={year_obj.id}&term={term_obj.id}")

    if request.method == "POST" and request.POST.get("action") == "update_weights":
        if weights_form.is_valid():
            data = weights_form.cleaned_data
            term_value = data.get("term")
            classroom_value = data.get("classroom")
            classroom_id_target = classroom_value.id if classroom_value else 0
            term_locked = False
            if term_value:
                term_locked = is_term_published(
                    data["academic_year"].id,
                    term_value.id,
                    classroom_id_target,
                )
            if term_locked:
                messages.error(
                    request,
                    "Assessment weights cannot be changed because the selected term has been published.",
                )
            else:
                AssessmentWeights.objects.update_or_create(
                    academic_year=data["academic_year"],
                    term=term_value,
                    classroom=classroom_value,
                    defaults={
                        "seq1_weight": data["seq1_weight"],
                        "seq2_weight": data["seq2_weight"],
                        "exam_weight": data["exam_weight"],
                        "mock_weight": data["mock_weight"],
                        "practical_weight": data["practical_weight"],
                        "score_scale": data["score_scale"],
                    },
                )
                messages.success(request, "Assessment weights saved.")
                redirect_target = request.path + f"?year={year_obj.id}&term={term_obj.id}"
                if classroom_id:
                    redirect_target += f"&classroom={classroom_id}"
                return redirect(redirect_target)

    evals = Evaluation.objects.filter(academic_year=year_obj, term=term_obj).select_related(
        "student",
        "teacher",
        "subject_assignment__classroom",
        "subject_assignment__specialty",
        "subject_assignment__subject",
    ).prefetch_related("evidence")

    if classroom_obj:
        evals = evals.filter(subject_assignment__classroom=classroom_obj)
    if subject_id:
        evals = evals.filter(subject_assignment__subject_id=subject_id)

    required_fields = _required_fields(year_obj, classroom_obj, term_obj)
    evals_list = list(evals.order_by("-updated_at"))
    if missing_only:
        evals_list = [
            e for e in evals_list
            if any(getattr(e, field) is None for field in _required_fields_for_evaluation(e))
        ]

    if request.method == "POST" and request.POST.get("action") == "fill_missing":
        if fill_form.is_valid():
            fill_value = Decimal(fill_form.cleaned_data["fill_value"])
            updated = 0
            for evaluation in evals_list:
                needs_update = False
                updates = {}
                for field in _required_fields_for_evaluation(evaluation):
                    if getattr(evaluation, field) is None:
                        updates[field] = fill_value
                        needs_update = True
                if needs_update:
                    Evaluation.objects.filter(id=evaluation.id).update(**updates)
                    updated += 1
            messages.success(request, f"Filled missing scores for {updated} evaluations.")
            redirect_target = request.path + f"?year={year_obj.id}&term={term_obj.id}"
            if classroom_id:
                redirect_target += f"&classroom={classroom_id}"
            if subject_id:
                redirect_target += f"&subject={subject_id}"
            if missing_only:
                redirect_target += "&missing=1"
            return redirect(redirect_target)

    subject_obj = Subject.objects.filter(id=subject_id).first() if subject_id else None
    filters = {
        "Classroom": classroom_obj.name if classroom_obj else None,
        "Subject": subject_obj.name if subject_obj else None,
        "Missing": "Yes" if missing_only else "All",
    }

    if request.GET.get("export") == "pdf":
        rows = [_serialize_evaluation(e) for e in evals_list]
        pdf_context = {
            "report_title": f"Evaluation Manager · {year_obj.name}",
            "report_period": term_obj.label,
            "report_total": f"{len(rows)} rows",
            "rows": rows,
            "filters": filters,
            "generated_at": timezone.now(),
            "summary": f"{len(rows)} evaluations",
        }
        pdf_bytes = render_pdf_bytes(request, "reports/evaluation_grid.html", pdf_context)
        filename = f"grading-sheet-{year_obj.name}-{term_obj.label}.pdf".replace(" ", "_")
        response = HttpResponse(pdf_bytes, content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response

    if request.GET.get("export") == "csv":
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = f'attachment; filename="grading-sheet-{year_obj.name}-{term_obj.label}.csv"'
        writer = csv.writer(response)
        writer.writerow([
            "Student Code",
            "Student Name",
            "Classroom",
            "Specialty",
            "Subject",
            "Seq 1",
            "Seq 2",
            "Exam",
            "Mock",
            "Practical",
            "Total",
        ])
        for e in evals_list:
            writer.writerow([
                e.student.student_code,
                f"{e.student.last_name} {e.student.first_name}",
                e.subject_assignment.classroom.name,
                e.subject_assignment.specialty.name,
                e.subject_assignment.subject.name,
                e.seq1_score or "",
                e.seq2_score or "",
                e.exam_score or "",
                e.mock_score or "",
                e.practical_score or "",
                f"{e.total_score:.2f}",
            ])
        return response

    export_csv_params = request.GET.copy()
    export_csv_params["export"] = "csv"
    export_pdf_params = request.GET.copy()
    export_pdf_params["export"] = "pdf"

    return render(request, "evals/evaluation_admin.html", {
        "year": year_obj,
        "term": term_obj,
        "selected_year": year_obj,
        "selected_term": term_obj,
        "filter_form": filter_form,
        "create_form": create_form,
        "weights_form": weights_form,
        "fill_form": fill_form,
        "current_weights": current_weights,
        "evals": evals_list,
        "missing_only": missing_only,
        "required_fields": required_fields,
        "export_csv_query": export_csv_params.urlencode(),
        "export_pdf_query": export_pdf_params.urlencode(),
    })


@staff_member_required
def evaluation_evidence_upload(request: HttpRequest):
    evaluation_id = request.GET.get("evaluation")
    evaluation = None
    if evaluation_id:
        evaluation = get_object_or_404(Evaluation, id=evaluation_id)

    form = EvaluationEvidenceForm(
        data=request.POST or None,
        files=request.FILES or None,
        evaluation=evaluation,
    )

    if request.method == "POST" and form.is_valid():
        evidence = form.save(commit=False)
        evidence.uploaded_by = request.user
        evidence.save()
        messages.success(request, "Evidence uploaded successfully.")
        return redirect("evals:evaluation_admin")

    evidence_items = EvaluationEvidence.objects.select_related(
        "evaluation",
        "evaluation__student",
        "evaluation__subject_assignment__subject",
    ).order_by("-uploaded_at")[:50]

    return render(request, "evals/evidence_upload.html", {
        "form": form,
        "evaluation": evaluation,
        "evidence_items": evidence_items,
    })

class GradeImportUploadForm(forms.Form):
    file = forms.FileField(help_text="Upload a CSV with the expected headers.")


@staff_member_required
def grade_import_upload_view(request: HttpRequest):
    """
    Staff-facing CSV upload with preview + apply.
    """
    form = GradeImportUploadForm(request.POST or None, request.FILES or None)
    preview = None
    result = None
    active_year, _ = get_active_year_and_term()
    if request.method == "POST" and form.is_valid():
        upload = form.cleaned_data["file"]
        try:
            reader = csv.DictReader(io.TextIOWrapper(upload, encoding="utf-8"))
            preview = preview_import(reader)
        except Exception as exc:  # pragma: no cover - defensive
            messages.error(request, f"Could not read CSV: {exc}")
        else:
            if preview.errors:
                messages.error(request, "Please fix the errors below before applying.")
            elif request.POST.get("action") == "apply":
                if not active_year:
                    messages.error(request, "No active academic year found.")
                else:
                    result = apply_import(preview, active_year)
                    messages.success(request, f"Imported grades (created: {result['created']}, updated: {result['updated']}).")
    return render(request, "evals/grade_import_upload.html", {
        "form": form,
        "preview": preview,
        "result": result,
        "template_headers": build_template_headers(),
        "active_year": active_year,
    })


@staff_member_required
def grade_import_template_view(request: HttpRequest):
    """
    Serve a CSV template for bulk grade imports (same fields as the management command).
    """
    fieldnames = [
        "student_code",
        "subject_assignment_id",
        "term_id",
        "teacher_username",
        "seq1",
        "seq2",
        "exam",
        "mock",
        "practical",
        "test1",
        "test2",
        "remarks",
    ]
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename=\"grade_import_template.csv\"'
    writer = csv.DictWriter(response, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerow({})
    return response

@staff_member_required
def grade_approval_list(request: HttpRequest):
    if not _user_can_review_grades(request.user):
        return HttpResponseForbidden("You are not authorized to review grade approvals.")

    status_filter = request.GET.get("status")
    qs = GradeApprovalRequest.objects.select_related(
        "teacher__user",
        "subject_assignment__subject",
        "term",
        "academic_year",
    ).order_by("-requested_at")
    if status_filter in GradeApprovalRequest.Status.values:
        qs = qs.filter(status=status_filter)

    context = {
        "requests": qs,
        "status_filter": status_filter or "",
        "status_options": [("", "All")] + list(GradeApprovalRequest.Status.choices),
    }
    return render(request, "evals/grade_approval_list.html", context)


@staff_member_required
def grade_approval_detail(request: HttpRequest, request_id):
    approval = get_object_or_404(GradeApprovalRequest, id=request_id)
    if not _user_can_review_grades(request.user):
        return HttpResponseForbidden("You are not authorized to review grade approvals.")

    can_finalize = user_can_finalize_submission(request.user)
    status_choices = list(GradeApprovalRequest.Status.choices)
    if not can_finalize:
        status_choices = [choice for choice in status_choices if choice[0] not in FINAL_STATUSES]
    form = GradeApprovalDecisionForm(
        request.POST or None,
        initial={"status": approval.status},
        status_choices=status_choices,
    )
    if request.method == "POST" and form.is_valid():
        new_status = form.cleaned_data["status"]
        if new_status in FINAL_STATUSES and not can_finalize:
            form.add_error("status", "Only final approvers can finalize or reject grade submissions.")
        else:
            approval.mark_reviewed(
                reviewer=request.user,
                status=new_status,
                notes=form.cleaned_data["reviewer_notes"],
            )
            NotificationService().send_grade_approval_decision_email(approval, new_status)
            messages.success(request, "Grade approval decision saved.")
            return redirect("evals:grade_approval_list")

    deadline_note = getattr(SiteSettings.get_solo(), "grade_approval_deadline_note", "")
    deadline_display = approval.deadline_at.strftime("%b %d, %Y %H:%M") if approval.deadline_at else None
    validation_flags = approval.validation_flags or []
    return render(request, "evals/grade_approval_detail.html", {
        "approval": approval,
        "form": form,
        "entries": approval.entries,
        "score_fields": ["seq1", "seq2", "exam", "mock", "practical"],
        "can_finalize": can_finalize,
        "deadline_display": deadline_display,
        "deadline_note": deadline_note,
        "deadline_overdue": approval.is_overdue,
        "validation_flags": validation_flags,
        "final_roles": grade_post_roles(),
    })

# ========== COMPLIANCE & ADVANCED IMPORT VIEWS ==========

@staff_member_required
@role_required(User.Role.ADMIN, 'head_of_academics')
def compliance_dashboard_view(request):
    """
    Dashboard showing teacher grading compliance status.
    
    Displays:
    - KPI cards (compliant, at-risk, overdue teachers)
    - Compliance table with filter/sort
    - Deadline extensions modal
    """
    from apps.analytics.services import get_teacher_compliance
    
    academic_year, term = get_active_year_and_term()
    
    if not academic_year or not term:
        messages.warning(request, "No active academic year or term.")
        return redirect("admin:index")
    
    # Get compliance data
    compliance_data = get_teacher_compliance(academic_year.id, term.id)
    
    # Calculate KPIs
    total_teachers = len(compliance_data)
    compliant_count = sum(1 for t in compliance_data if t['status'] == 'compliant')
    at_risk_count = sum(1 for t in compliance_data if t['status'] == 'at_risk')
    overdue_count = sum(1 for t in compliance_data if t['status'] == 'overdue')
    
    # Filter by status if requested
    status_filter = request.GET.get('status', 'all')
    if status_filter != 'all':
        compliance_data = [t for t in compliance_data if t['status'] == status_filter]
    
    context = {
        'compliance_data': compliance_data,
        'kpis': {
            'total': total_teachers,
            'compliant': compliant_count,
            'at_risk': at_risk_count,
            'overdue': overdue_count,
        },
        'current_term': f"{academic_year.name} - {term.name}",
        'status_filter': status_filter,
    }
    
    return render(request, 'evals/compliance_dashboard.html', context)


@staff_member_required
@role_required(User.Role.ADMIN, 'head_of_academics')
def extend_deadline_view(request, subject_assignment_id):
    """Extend grading deadline for a subject assignment."""
    from apps.analytics.models import GradingDeadline
    
    academic_year, term = get_active_year_and_term()
    SubjectAssignment = __import__('apps.academics.models', fromlist=['SubjectAssignment']).SubjectAssignment
    
    try:
        subject_assignment = SubjectAssignment.objects.get(id=subject_assignment_id)
        deadline = GradingDeadline.objects.get(
            academic_year=academic_year,
            term=term,
            subject_assignment=subject_assignment
        )
    except (SubjectAssignment.DoesNotExist, GradingDeadline.DoesNotExist):
        messages.error(request, "Deadline not found.")
        return redirect('compliance_dashboard')
    
    if request.method == 'POST':
        days_extension = int(request.POST.get('days_extension', 0))
        reason = request.POST.get('reason', '')
        
        if days_extension > 0:
            new_deadline = deadline.deadline_date + timezone.timedelta(days=days_extension)
            deadline.deadline_date = new_deadline
            deadline.save()
            
            # Log in audit trail
            from apps.evals.models import GradeAudit
            GradeAudit.objects.create(
                evaluation=None,  # Not linked to specific evaluation
                change_type='deadline_extended',
                changed_by=request.user,
                remarks_after=f"Deadline extended by {days_extension} days. Reason: {reason}"
            )
            
            messages.success(request, f"Deadline extended to {new_deadline.date()}")
        
        return redirect('compliance_dashboard')
    
    return render(request, 'evals/extend_deadline.html', {
        'deadline': deadline,
        'subject_assignment': subject_assignment,
    })


@staff_member_required
@role_required(User.Role.ADMIN, 'head_of_academics')
def grade_import_preview_api(request):
    """API endpoint for grade import preview with validation."""
    from apps.evals.importers import preview_import_with_validation
    import json
    
    if request.method != 'POST':
        return HttpResponseForbidden("POST required")
    
    # Parse CSV from request
    csv_file = request.FILES.get('file')
    if not csv_file:
        return HttpResponse(json.dumps({'error': 'No file provided'}), content_type='application/json', status=400)
    
    try:
        import csv as csv_module
        reader = csv_module.DictReader(io.TextIOWrapper(csv_file, encoding='utf-8'))
        csv_rows = list(reader)
        
        # Run validation
        rows_with_validation, errors = preview_import_with_validation(csv_rows)
        
        # Return preview
        preview_data = []
        for row in rows_with_validation:
            preview_data.append({
                'student_code': row.student_code,
                'subject_assignment_id': row.subject_assignment_id,
                'term_id': row.term_id,
                'seq1': row.seq1,
                'seq2': row.seq2,
                'exam': row.exam,
                'is_valid': row.is_valid,
                'errors': row.errors,
                'warnings': row.warnings,
            })
        
        return HttpResponse(json.dumps({
            'preview': preview_data,
            'file_errors': errors,
            'total_rows': len(rows_with_validation),
            'valid_rows': sum(1 for r in rows_with_validation if r.is_valid),
            'invalid_rows': sum(1 for r in rows_with_validation if not r.is_valid),
        }), content_type='application/json')
    
    except Exception as e:
        return HttpResponse(json.dumps({'error': str(e)}), content_type='application/json', status=400)


@staff_member_required
@role_required(User.Role.ADMIN, 'head_of_academics')
def grade_import_apply_api(request):
    """API endpoint for applying (persisting) grade import."""
    from apps.evals.importers import apply_import
    from apps.analytics.models import GradeImportJob
    import json
    
    if request.method != 'POST':
        return HttpResponseForbidden("POST required")
    
    # Create job record
    job = GradeImportJob.objects.create(
        status='processing',
        created_count=0,
        updated_count=0,
        failed_count=0,
    )
    
    try:
        csv_file = request.FILES.get('file')
        csv_module = __import__('csv')
        reader = csv_module.DictReader(io.TextIOWrapper(csv_file, encoding='utf-8'))
        csv_rows = list(reader)
        
        # Apply import
        result = apply_import(csv_rows)
        
        # Update job
        job.created_count = result['created']
        job.updated_count = result['updated']
        job.status = 'completed'
        job.completed_at = timezone.now()
        job.save()
        
        return HttpResponse(json.dumps({
            'job_id': job.id,
            'status': 'completed',
            'created': result['created'],
            'updated': result['updated'],
            'duration_seconds': result.get('duration_seconds', 0),
        }), content_type='application/json')
    
    except Exception as e:
        job.status = 'failed'
        job.failed_count += 1
        job.error_log = [str(e)]
        job.save()
        
        return HttpResponse(json.dumps({
            'job_id': job.id,
            'status': 'failed',
            'error': str(e),
        }), content_type='application/json', status=400)


@staff_member_required
@role_required(User.Role.ADMIN, 'head_of_academics', User.Role.TEACHER)
def audit_trail_view(request, evaluation_id):
    """View audit trail for an evaluation."""
    from apps.analytics.services import get_audit_trail
    
    try:
        evaluation = Evaluation.objects.get(id=evaluation_id)
    except Evaluation.DoesNotExist:
        messages.error(request, "Evaluation not found.")
        return redirect("admin:evals_evaluation_changelist")
    
    trail = get_audit_trail(evaluation_id, limit=100)
    
    context = {
        'evaluation': evaluation,
        'trail': trail,
        'student_name': f"{evaluation.student.user.first_name} {evaluation.student.user.last_name}",
        'subject_name': evaluation.subject_assignment.subject.name,
    }
    
    return render(request, 'evals/audit_trail.html', context)


@staff_member_required
@role_required(User.Role.ADMIN, 'head_of_academics')
def resolve_offline_conflict_view(request, offline_entry_id):
    """Manual conflict resolution for offline mark entries."""
    from apps.evals.models import OfflineMarkEntry
    
    try:
        offline_entry = OfflineMarkEntry.objects.get(id=offline_entry_id)
    except OfflineMarkEntry.DoesNotExist:
        messages.error(request, "Offline entry not found.")
        return redirect("admin:evals_offlinemarkentry_changelist")
    
    if offline_entry.status != 'conflict':
        messages.info(request, "This entry is not in conflict status.")
        return redirect("admin:evals_offlinemarkentry_changelist")
    
    # Get online version
    try:
        online_entry = Evaluation.objects.get(
            academic_year=offline_entry.academic_year,
            term=offline_entry.term,
            subject_assignment=offline_entry.subject_assignment,
            student=offline_entry.student,
        )
    except Evaluation.DoesNotExist:
        online_entry = None
    
    if request.method == 'POST':
        # User chose to keep online or offline version
        choice = request.POST.get('choice', 'online')
        
        if choice == 'offline' and online_entry:
            # Merge offline into online
            online_entry.seq1_score = offline_entry.seq1_score
            online_entry.seq2_score = offline_entry.seq2_score
            online_entry.exam_score = offline_entry.exam_score
            online_entry.mock_score = offline_entry.mock_score
            online_entry.practical_score = offline_entry.practical_score
            online_entry.remarks = offline_entry.remarks
            online_entry.save()
        
        # Mark as resolved
        offline_entry.status = 'synced'
        offline_entry.save()
        
        messages.success(request, "Conflict resolved.")
        return redirect("admin:evals_offlinemarkentry_changelist")
    
    context = {
        'offline_entry': offline_entry,
        'online_entry': online_entry,
        'student_name': f"{offline_entry.student.user.first_name} {offline_entry.student.user.last_name}",
        'subject_name': offline_entry.subject_assignment.subject.name,
    }
    
    return render(request, 'evals/resolve_offline_conflict.html', context)

@staff_member_required
@role_required(User.Role.ADMIN, 'head_of_academics')
def import_job_monitor_view(request):
    """Monitor and manage import jobs."""
    from apps.analytics.models import GradeImportJob
    
    # Get filter parameters
    status_filter = request.GET.get('status', '')
    from_date = request.GET.get('from_date', '')
    to_date = request.GET.get('to_date', '')
    
    # Build query
    query = GradeImportJob.objects.all().order_by('-created_at')
    
    if status_filter:
        query = query.filter(status=status_filter)
    
    if from_date:
        from datetime import datetime
        try:
            from_datetime = datetime.fromisoformat(from_date)
            query = query.filter(created_at__gte=from_datetime)
        except ValueError:
            pass
    
    if to_date:
        from datetime import datetime
        try:
            to_datetime = datetime.fromisoformat(to_date)
            query = query.filter(created_at__lte=to_datetime)
        except ValueError:
            pass
    
    # Get jobs (limit to last 50 for performance)
    jobs = query[:50]
    
    # Calculate summary stats
    all_jobs = GradeImportJob.objects.all()
    total_jobs = all_jobs.count()
    processing_jobs = all_jobs.filter(status='processing').count()
    completed_jobs = all_jobs.filter(status='completed').count()
    failed_jobs = all_jobs.filter(status='failed').count()
    
    context = {
        'jobs': jobs,
        'total_jobs': total_jobs,
        'processing_jobs': processing_jobs,
        'completed_jobs': completed_jobs,
        'failed_jobs': failed_jobs,
        'status': status_filter,
        'from_date': from_date,
        'to_date': to_date,
    }
    
    return render(request, 'evals/import_job_monitor.html', context)
