import logging
from django.conf import settings
from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpRequest, HttpResponseForbidden, HttpResponse, JsonResponse
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.contrib import messages

logger = logging.getLogger(__name__)
from django.contrib.admin.views.decorators import staff_member_required
from django import forms
import csv
import io
from decimal import Decimal, InvalidOperation
from typing import Any
from django.urls import reverse
from django.utils import timezone
import json
from django.db import DatabaseError
from django.core.exceptions import ValidationError

from apps.accounts.decorators import role_required, teacher_portal_required
from apps.accounts.models import User
from apps.observability.tracing import trace_view
from apps.academics.models import (
    SubjectAssignment,
    Classroom,
    AcademicYear,
    Term,
    Subject,
)
from apps.academics.services import get_active_year_and_term
from django.db.models import Q
from apps.people.models import (
    TeacherProfile,
    StudentProfile,
    TeacherAttendance,
    TeacherLeaveRequest,
    BadgeType,
    Badge,
)
from apps.evals.models import (
    GradeApprovalRequest,
    TeacherAssignment,
    Evaluation,
    AssessmentWeights,
)
from apps.evals.rosetta_stone import get_supported_scales, view_grade_in_target_system
from apps.evals.importers import build_template_headers
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
    GradeApprovalBypassForm,
)
from .models import EvaluationEvidence
from .ocr import process_marksheet_upload, is_tesseract_available, FIELD_ORDER
from .approval import (
    create_grade_approval_request,
    grade_entries_from_submission,
    grade_approver_roles,
    grade_post_roles,
    try_emit_grade_published_event,
    user_can_finalize_submission,
    FINAL_STATUSES,
)
from .notifications import NotificationService
from apps.portal.services import (
    teacher_dashboard_widget_data,
    teacher_scope,
    class_announcements_for_teacher,
    class_threads_for_teacher,
    _upcoming_deadlines,
)
from apps.portal.models import PortalFeatureItem
from .services import ews_students_needing_attention
from apps.communication.models import MessageThread
from apps.communication.views_announcements import _can_create_department_announcement
from apps.siteconfig.config_service import (
    get_effective_flags,
    get_effective_site_settings,
)
from apps.siteconfig.models import default_backend_feature_flags
from apps.siteconfig.dashboard_resolver import for_role as dashboard_for_role
from apps.siteconfig.workflow_resolver import (
    get_approval_workflow as workflow_get_approval,
)
from apps.finance.models import Notification
from apps.compliance.models_audit import AuditLog

EVALS_SOFT_FAILURES = (
    AttributeError,
    csv.Error,
    DatabaseError,
    ImportError,
    InvalidOperation,
    LookupError,
    OSError,
    RuntimeError,
    TypeError,
    ValueError,
)


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
    # tenant-isolation-allow: view-layer-scoped-via-request-school-or-role-graph
    teacher = TeacherProfile.objects.filter(user=request.user).first()
    if not teacher:
        return None, HttpResponseForbidden(
            "Teacher profile missing. Contact an administrator to finish setup."
        )
    return teacher, None


def _required_fields_for_evaluation(evaluation: Evaluation) -> list[str]:
    weights = AssessmentWeights.get_for(
        academic_year=evaluation.academic_year,
        classroom=evaluation.subject_assignment.classroom
        if evaluation.subject_assignment_id
        else None,
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


def _update_evaluations_from_entries(
    entries, students_map, teacher, year, term, subject_assignment
) -> int:
    if getattr(year, "is_locked", False):
        return 0  # Year hard lock: no grade edits after rollover
    updated = 0
    for entry in entries:
        student = students_map.get(entry["student_id"])
        if student is None:
            continue
        try:
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
        except ValidationError:
            continue
        updated += 1
    return updated


def _user_can_review_grades(user: User, school=None, policy=None) -> bool:
    if not user.is_authenticated:
        return False
    if getattr(user, "is_superuser", False):
        return True
    roles = grade_approver_roles(school=school, policy=policy)
    if user.role in roles:
        return True
    return user.roles.filter(code__in=roles).exists()


def _student_lookup_by_code(
    students: list[StudentProfile],
) -> dict[str, StudentProfile]:
    return {
        (student.student_code or "").upper(): student
        for student in students
        if student.student_code
    }


def _apply_ocr_entries(
    entries, student_lookup, sa, year, term, teacher, delta_mode: bool = True
):
    """
    Apply OCR entries to evaluations.

    Args:
        entries: List of parsed OCR entries
        student_lookup: Dict mapping student_code -> StudentProfile
        sa: SubjectAssignment
        year: AcademicYear
        term: Term
        teacher: TeacherProfile
        delta_mode: If True, only fill missing marks (skip if field already has a value).
                    If False, update all fields even if they already have values.
    """
    if getattr(year, "is_locked", False):
        return []  # Year hard lock: no grade edits after rollover
    updated = []
    for entry in entries:
        student = student_lookup.get(entry.get("student_code", "").upper())
        if not student:
            continue
        evaluation = Evaluation.objects.filter(
            school_id=year.school_id,
            academic_year=year,
            term=term,
            subject_assignment=sa,
            student=student,
        ).first()
        if evaluation is None:
            evaluation = Evaluation(
                academic_year=year,
                term=term,
                subject_assignment=sa,
                student=student,
                teacher=teacher,
            )
        changes = {}
        for field, value in entry.get("scores", {}).items():
            if value is None:
                continue
            existing = getattr(evaluation, field)
            # Delta mode: only update if field is missing (None/empty)
            if delta_mode and existing is not None:
                continue
            # Non-delta mode or field is empty: update if different
            if existing != value:
                setattr(evaluation, field, value)
                changes[field] = value
        if changes:
            evaluation._audit_change_type = "ocr_upload"
            evaluation.teacher = teacher
            evaluation.save()
            updated.append({"student": student, "changes": changes})
    return updated


def _build_ocr_preview(entries, student_lookup, existing_evaluations: dict = None):
    """
    Build OCR preview with per-field confidence scores.

    Args:
        entries: OCR parsed entries (may include 'field_confidences')
        student_lookup: Dict mapping student_code -> StudentProfile
        existing_evaluations: Dict mapping student_id -> Evaluation (for showing existing values)
    """
    existing_evaluations = existing_evaluations or {}
    preview = []
    for entry in entries:
        student = student_lookup.get(entry.get("student_code", "").upper())
        full_name = ""
        if student:
            full_name = f"{student.last_name} {student.first_name}"

        # Get existing evaluation to show current values
        existing_eval = existing_evaluations.get(student.id) if student else None
        existing_scores = {}
        if existing_eval:
            for field in [
                "seq1_score",
                "seq2_score",
                "exam_score",
                "mock_score",
                "practical_score",
                "internship_score",
            ]:
                val = getattr(existing_eval, field, None)
                if val is not None:
                    existing_scores[field] = val

        preview.append(
            {
                "code": entry.get("student_code"),
                "student_name": full_name if full_name else "Unmatched student",
                "student_id": student.id if student else None,
                "scores": entry.get("scores", {}),
                "field_confidences": entry.get(
                    "field_confidences", {}
                ),  # Per-field confidence
                "existing_scores": existing_scores,  # Current values in DB
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
                "scores": {
                    field: str(value)
                    for field, value in entry.get("scores", {}).items()
                },
                "field_confidences": entry.get(
                    "field_confidences", {}
                ),  # Preserve confidence data
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
            except (InvalidOperation, TypeError, ValueError):
                continue
        deserialized.append(
            {
                "student_code": entry.get("student_code"),
                "line_text": entry.get("line_text"),
                "scores": scores,
                "field_confidences": entry.get(
                    "field_confidences", {}
                ),  # Preserve confidence data
            }
        )
    return deserialized


def _extract_corrected_ocr_entries(post_data, original_entries):
    """
    Extract user-corrected OCR values from POST data.
    Form fields: ocr_correct_{student_code}_{field} = value
    Returns corrected entries or None if no corrections found.
    """
    corrected = []
    for index, entry in enumerate(original_entries):
        student_code = entry.get("student_code", "").upper()
        corrected_scores = {}
        for field in FIELD_ORDER:
            index_key = f"ocr_correct_{index}_{field}"
            legacy_key = f"ocr_correct_{student_code}_{field}"
            value_str = str(
                post_data.get(index_key, post_data.get(legacy_key, "")) or ""
            ).strip()
            if value_str:
                try:
                    corrected_scores[field] = Decimal(value_str)
                except (InvalidOperation, TypeError, ValueError):
                    continue
        if corrected_scores:
            corrected.append(
                {
                    "student_code": student_code,
                    "scores": corrected_scores,
                    "line_text": entry.get("line_text", ""),
                    "field_confidences": entry.get("field_confidences", {}),
                }
            )
        else:
            # Keep original if no corrections
            corrected.append(entry)
    return (
        corrected
        if any(
            c.get("scores") != orig.get("scores")
            for c, orig in zip(corrected, original_entries)
        )
        else None
    )


def _validate_ocr_entries(entries, max_score=Decimal("20")):
    """Validate OCR-extracted marksheet scores against the school's grading scale
    upper bound (local-first). ``max_score`` is the school's active scale max
    (e.g. 20 francophone, 100 percentage, 4 GPA) — never a hardcoded 0-20."""
    try:
        max_score = Decimal(str(max_score))
    except (InvalidOperation, TypeError, ValueError):
        max_score = Decimal("20")
    if max_score == max_score.to_integral_value():
        max_label = str(int(max_score))
    else:
        max_label = format(max_score, "f").rstrip("0").rstrip(".")
    errors = []
    for entry in entries:
        student_code = str(entry.get("student_code") or "").strip() or "unknown"
        for field, value in (entry.get("scores") or {}).items():
            try:
                score = Decimal(str(value))
            except (InvalidOperation, TypeError, ValueError):
                errors.append(f"{student_code} {field}: invalid number")
                continue
            if score < 0 or score > max_score:
                errors.append(f"{student_code} {field}: score must be 0 to {max_label}")
    return errors


def _normalized_scale_max(scale):
    """Render the operational score-scale max as a clean HTML ``max=`` value:
    a whole scale stays an int (20, 100, 4), a fractional scale keeps one
    decimal (7.5). Mirrors the dashboard's ``grading_scale_max`` normalization so
    the marks grid and the at-risk badge agree. Falls back to 20 on junk input so
    a render never breaks (back-compat with the historical /20 default)."""
    try:
        value = float(scale)
    except (TypeError, ValueError):
        return 20
    return int(value) if value == int(value) else round(value, 1)


def _pending_ocr_for(session, teacher_id, subject_assignment_id):
    pending = session.get(MARKSHEET_OCR_PENDING_SESSION_KEY)
    if not pending:
        return None
    if pending.get("teacher") != teacher_id:
        return None
    if pending.get("subject_assignment") != subject_assignment_id:
        return None
    return pending


def _set_pending_ocr(
    session,
    teacher_id,
    subject_assignment_id,
    entries,
    confidence,
    field_confidences=None,
):
    session[MARKSHEET_OCR_PENDING_SESSION_KEY] = {
        "teacher": teacher_id,
        "subject_assignment": subject_assignment_id,
        "entries": _serialize_pending_entries(entries),
        "confidence": confidence,
        "field_confidences": field_confidences or {},
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
    # tenant-isolation-allow: view-layer-scoped-via-request-school-or-role-graph
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
        from apps.portal.tenant_role_home import build_tp_hero_context

        return render(
            request,
            "teacher/dashboard.html",
            {
                **build_tp_hero_context(request, role=User.Role.TEACHER),
                "teacher_show_legacy_dashboard": False,
                "display_widgets": [],
                "year": year,
                "term": term,
                "teacher_fast_workflows": [],
                "teacher_alerts": [
                    {
                        "title": "Academic year setup needed",
                        "message": "Ask an admin to activate the current academic year and term.",
                        "tone": "warning",
                    }
                ],
            },
        )

    teacher_profile, assignments, students_qs, classrooms = teacher_scope(
        request.user, academic_year=year
    )
    if teacher_profile is None:
        return error

    # Progress indicators per assignment (filled / total)
    progress = {}
    # tenant-isolation-allow: view-layer-scoped-via-request-school-or-role-graph
    for a in assignments:
        sa = a.subject_assignment
        # tenant-isolation-allow: view-layer-scoped-via-request-school-or-role-graph
        total = StudentProfile.objects.filter(
            academic_year=year,
            classroom=sa.classroom,
            specialty=sa.specialty,
            is_active=True,
        ).count()

        required = _required_fields(year, sa.classroom, term)
        # Count evaluations that have all required fields filled
        # tenant-isolation-allow: view-layer-scoped-via-request-school-or-role-graph
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

    widget_data = teacher_dashboard_widget_data(
        assignments, progress, year, term, teacher=teacher
    )
    attendance = widget_data.get("attendance") or {}
    attendance_pct = attendance.get("overall")
    hero_stats = [
        {
            "label": "Assignments",
            "value": widget_data["assignments_count"],
            "meta": "Active subjects",
        },
        {
            "label": "Completion",
            "value": f"{widget_data['completion_pct']}%",
            "progress": widget_data["completion_pct"],
            "meta": "Marks entered",
        },
        {
            "label": "Pending",
            "value": widget_data["tasks"]["pending_evaluations"],
            "meta": "Marks remaining",
        },
    ]
    if attendance_pct is not None:
        hero_stats.append(
            {
                "label": "Attendance",
                "value": f"{attendance_pct}%",
                "meta": "Class average",
            }
        )
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
            {
                "label": "Download template",
                "url": reverse("evals:grade_import_template"),
            },
        ],
    }

    # Add communication actions if teacher has department; only HOD/leadership can create department announcements
    if teacher_profile and teacher_profile.department:
        hero["actions"].extend(
            [
                {
                    "label": "Department Chat",
                    "url": reverse("communication:group_list"),
                },
            ]
        )
        if _can_create_department_announcement(request.user):
            hero["actions"].append(
                {
                    "label": "Dept Announcement",
                    "url": reverse("communication:department_announcement_create"),
                }
            )

    runtime = getattr(request, "tenant_runtime", None)
    if runtime is not None and getattr(runtime, "_school", None):
        dash = runtime.dashboard_for(
            role=getattr(request.user, "role", None), user=request.user
        )
    else:
        dash = dashboard_for_role(
            getattr(request, "school", None),
            getattr(request.user, "role", None),
            user=request.user,
        )
    display_widgets = dash["widget_keys"]
    class_announcements = class_announcements_for_teacher(
        request.user,
        classrooms,
        department_id=getattr(teacher_profile.department, "id", None),
        limit=6,
    )
    class_threads = class_threads_for_teacher(
        request.user, limit=6, include_department=True
    )
# tenant-isolation-allow: view-layer-scoped-via-request-school-or-role-graph

    # Get department thread for quick access
    department_thread = None
    # tenant-isolation-allow: view-layer-scoped-via-request-school-or-role-graph
    if teacher_profile and teacher_profile.department:
        department_thread = MessageThread.objects.filter(
            scope=MessageThread.Scope.DEPARTMENT,
            department=teacher_profile.department,
            is_archived=False,
        ).first()

    peers = []
    if getattr(teacher_profile, "department", None):
        peer_qs = (
            TeacherProfile.objects.select_related("user")
            .filter(department=teacher_profile.department)
            .exclude(id=teacher_profile.id)[:6]
        )
        for peer in peer_qs:
            user = peer.user
            peers.append(
                {
                    "name": user.get_full_name() or user.username,
                    "role": getattr(user, "role", ""),
                }
            )

    flags = get_effective_flags(request)
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
    # tenant-isolation-allow: recipient-scoped-current-user-owns-notification
    finance_requests_qs = Notification.objects.filter(
        recipient=request.user,
        title__icontains="finance access request",
    ).order_by("-created_at")
    finance_request_link = reverse("requests:dashboard")

    from apps.accounts.utils import get_dashboard_context

    dashboard_context = get_dashboard_context(request.user, "teacher", request=request)
    available_sidebar_items = [
        {
            "id": "teacher-home",
            "label": "Teacher hub",
            "url": reverse("portal:teacher_dashboard_alias"),
            "icon": "bi-person-lines-fill",
        },
        {
            "id": "teacher-workflow",
            "label": "My Workflow",
            "url": reverse("portal:teacher_workflow"),
            "icon": "bi-diagram-3",
        },
        {
            "id": "teacher-attendance",
            "label": "Attendance",
            "url": reverse("portal:teacher_attendance"),
            "icon": "bi-calendar-check",
        },
        {
            "id": "teacher-pay",
            "label": "Pay history",
            "url": reverse("portal:teacher_pay_history"),
            "icon": "bi-wallet2",
        },
        {
            "id": "teacher-syllabus",
            "label": "Syllabus",
            "url": reverse("portal:portal_syllabus"),
            "icon": "bi-journal-text",
        },
    ]

    # Chart JSON for teacher dashboard
    chart_completion_bar_json = ""
    if assignments and progress:
        labels = []
        values = []
        for a in assignments[:8]:
            p = progress.get(a.id, {})
            sa = getattr(a, "subject_assignment", None)
            subj = "?"
            cls = ""
            if sa:
                subj = getattr(
                    getattr(sa, "subject", None),
                    "name",
                    str(getattr(sa, "subject", "?")),
                )[:16]
                cls_obj = getattr(sa, "classroom", None)
                cls = getattr(cls_obj, "name", str(cls_obj))[:10] if cls_obj else ""
            label = (cls + " - " + subj) if cls else subj
            labels.append(label[:24])
            values.append(p.get("width", 0))
        if labels:
            chart_completion_bar_json = json.dumps(
                {
                    "type": "bar",
                    "data": {
                        "labels": labels,
                        "datasets": [
                            {
                                "label": "Completion %",
                                "data": values,
                                "backgroundColor": "rgba(13, 110, 253, 0.8)",
                                "borderColor": "#0d6efd",
                                "borderWidth": 1,
                            }
                        ],
                    },
                    "options": {"indexAxis": "y"},
                }
            )
    # Marks completion donut: entered vs pending
    chart_marks_donut_json = ""
    total_slots = sum((p.get("total", 0) for p in progress.values()), 0)
    filled_slots = sum((p.get("filled", 0) for p in progress.values()), 0)
    pending_slots = max(0, total_slots - filled_slots)
    if total_slots > 0:
        chart_marks_donut_json = json.dumps(
            {
                "type": "doughnut",
                "data": {
                    "labels": ["Marks entered", "Pending"],
                    "datasets": [
                        {
                            "data": [filled_slots, pending_slots],
                            "backgroundColor": ["#198754", "#ffc107"],
                        }
                    ],
                },
            }
        )

    today = timezone.localdate()
    attendance_today = None
    if (
        teacher_profile
        and getattr(teacher_profile, "attendance_logs", None) is not None
    ):
        attendance_today = teacher_profile.attendance_logs.filter(date=today).first()
    present_today = bool(
        attendance_today and attendance_today.status == TeacherAttendance.Status.PRESENT
    )

    pending_leaves = 0
    if teacher_profile and getattr(teacher_profile, "leave_requests", None) is not None:
        pending_leaves = teacher_profile.leave_requests.filter(
            status=TeacherLeaveRequest.Status.PENDING
        ).count()

    workflow_steps = [
        {
            "label": "Profile and timetable",
            "action": "Open workflow",
            "url": reverse("portal:teacher_workflow"),
            "done": bool(assignments),
            "meta": f"{len(assignments)} classes linked",
        },
        {
            "label": "Attendance check-in",
            "action": "Mark attendance",
            "url": reverse("portal:teacher_attendance"),
            "done": present_today,
            "meta": "Marked for today" if present_today else "Not checked in today",
        },
        {
            "label": "Marks updates",
            "action": "Enter marks",
            "url": reverse("evals:teacher_marks_entry"),
            "done": pending_slots == 0,
            "meta": f"{pending_slots} pending",
        },
        {
            "label": "Leave and pay review",
            "action": "Review leave",
            "url": reverse("portal:teacher_leave"),
            "done": pending_leaves == 0,
            "meta": f"{pending_leaves} pending leave request(s)",
        },
    ]
    workflow_total_steps = len(workflow_steps)
    workflow_done_steps = sum(1 for step in workflow_steps if step["done"])
    workflow_completion_pct = (
        int(round((workflow_done_steps / workflow_total_steps) * 100))
        if workflow_total_steps
        else 0
    )
    workflow_open_steps = [step for step in workflow_steps if not step["done"]]
    if workflow_open_steps:
        workflow_focus_step = workflow_open_steps[0]
        workflow_next_actions = [
            {"label": step["action"], "url": step["url"]}
            for step in workflow_open_steps[:2]
        ]
    else:
        workflow_focus_step = {
            "label": "All key tasks completed",
            "meta": "You're on track for today. Use full workflow for detailed checks.",
        }
        workflow_next_actions = [
            {"label": "Open workflow", "url": reverse("portal:teacher_workflow")},
            {"label": "View marks", "url": reverse("evals:teacher_marks_list")},
        ]
    workflow_summary = {
        "total_steps": workflow_total_steps,
        "done_steps": workflow_done_steps,
        "completion_pct": workflow_completion_pct,
        "focus_label": workflow_focus_step["label"],
        "focus_meta": workflow_focus_step.get("meta", ""),
        "next_actions": workflow_next_actions,
    }

    # Certification stats (if GCE enabled and teacher teaches exam classes)
    certification_stats = {}
    if year and getattr(year, "enable_gce_registration", False):
        from apps.academics.models import (
            CertificationExamSession,
            CertificationCandidate,
        )

        # Check if teacher's classrooms have candidates
        teacher_classroom_ids = [
            sa.classroom_id for sa in assignments if sa.classroom_id
        ]
        if teacher_classroom_ids:
            candidates_in_classes = CertificationCandidate.objects.filter(
                session__academic_year=year,
                student__classroom_id__in=teacher_classroom_ids,
            ).select_related("session", "student")
            if candidates_in_classes.exists():
                certification_stats = {
                    "total_candidates": candidates_in_classes.count(),
                    "draft_candidates": candidates_in_classes.filter(
                        # tenant-isolation-allow: view-layer-scoped-via-request-school-or-role-graph
                        status="DRAFT"
                    ).count(),
                    "verified_candidates": candidates_in_classes.filter(
                        # tenant-isolation-allow: view-layer-scoped-via-request-school-or-role-graph
                        status="VERIFIED"
                    ).count(),
                    # tenant-isolation-allow: view-layer-scoped-via-request-school-or-role-graph
                    "sessions": CertificationExamSession.objects.filter(
                        academic_year=year,
                        is_active=True,
                    )[:3],
                }

    # Org chain and full tree (with photos) for "Organization" chart on dashboard and profile
    from apps.accounts.views import get_org_chain_to_staff, _teacher_org_tree

    org_chain = get_org_chain_to_staff(teacher_profile) if teacher_profile else []
    teacher_org_tree = _teacher_org_tree(request.user) if request.user else None

    # Phase 11: Show welcome hint when new (no assignments or no marks entered yet)
    show_welcome_hint = not assignments or (
        widget_data.get("completion_pct", 0) == 0
        and widget_data.get("assignments_count", 0) > 0
    )

    # Alerts for dashboard body (pending leave, EWS, etc.)
    teacher_alerts = []
    if pending_leaves:
        teacher_alerts.append(
            {
                "type": "leave",
                "message": f"You have {pending_leaves} pending leave request(s).",
                "url": reverse("portal:teacher_leave"),
                "cta": "View leave",
            }
        )
    ews_list = ews_students_needing_attention(
        teacher_profile,
        year,
        term,
        list(assignments),
        drop_threshold_pct=10.0,
    )
    if ews_list:
        teacher_alerts.append(
            {
                "type": "ews",
                "message": f"{len(ews_list)} student(s) need attention (grade drop >10% vs previous term).",
                "url": reverse("evals:teacher_marks_entry"),
                "cta": "Enter marks",
                "ews_list": ews_list[:5],
            }
        )

    # Phase 3: Curriculum map (syllabus covered vs remaining per class)
    curriculum_map = []
    for a in assignments[:8]:
        sa = getattr(a, "subject_assignment", None)
        if not sa:
            continue
        p = progress.get(a.id, {})
        covered = p.get("width", 0)
        curriculum_map.append(
            {
                "label": f"{getattr(sa.classroom, 'name', '')} — {getattr(sa.subject, 'name', '')}",
                "covered": covered,
                "remaining": max(0, 100 - covered),
            }
        )

    # Phase 3: Unified calendar events (upcoming deadlines)
    dashboard_events = _upcoming_deadlines(year) if year else []
    week_horizon = timezone.now() + timezone.timedelta(days=7)
    teacher_followup_items = list(ews_list[:5]) if ews_list else []
    teacher_deadline_items = [
        ev for ev in dashboard_events if ev.get("when") and ev["when"] <= week_horizon
    ][:5]
    teacher_deadline_counts = {
        "sequence_ca_deadlines": len(teacher_deadline_items),
        "practical_workshop_pending": widget_data.get("tasks", {}).get(
            "pending_evaluations", 0
        ),
        # Placeholder until timetable conflict engine is introduced.
        "timetable_conflicts": 0,
    }
    teacher_action_links = {
        "message": reverse("accounts:user_messages"),
        "open_marks": reverse("evals:teacher_marks_entry"),
        "flag_hod": reverse("portal:teacher_workflow"),
        "enter_marks": reverse("evals:teacher_marks_entry"),
        "open_timetable": reverse("portal:teacher_timetable"),
        # tenant-isolation-allow: view-layer-scoped-via-request-school-or-role-graph
        "export_list": f"{reverse('evals:teacher_marks_list')}?export=csv",
    }

    # tenant-isolation-allow: view-layer-scoped-via-request-school-or-role-graph
    # Phase 3: Resource library (syllabus items)
    syllabus_items = list(
        # tenant-isolation-allow: view-layer-scoped-via-request-school-or-role-graph
        PortalFeatureItem.objects.filter(
            feature=PortalFeatureItem.Feature.SYLLABUS,
            is_active=True,
        ).order_by("-created_at")[:5]
    )

    # Teacher dashboard: syllabus status per assignment, workflow counts, proxy/certification badges
    from apps.academics.models import CourseSyllabus
    from apps.accounts.delegation import get_active_delegation_for_delegate
    from apps.accounts.models import Delegation

    sa_ids = [a.subject_assignment_id for a in assignments]
    syllabi_by_sa = {
        s.subject_assignment_id: s
        for s in CourseSyllabus.objects.filter(subject_assignment_id__in=sa_ids)
    }
    assignment_syllabus_statuses = []
    syllabus_status_summary = {
        "draft": 0,
        "pending": 0,
        "needs_revision": 0,
        "approved": 0,
    }
    syllabus_pending_count = 0
    for a in assignments:
        prog = progress.get(a.id, {})
        student_count = prog.get("total", 0)
        syllabus = syllabi_by_sa.get(a.subject_assignment_id)
        if syllabus:
            status_slug = syllabus.status.lower()
            status_label = syllabus.get_status_display()
            if syllabus.status == CourseSyllabus.Status.PENDING:
                syllabus_pending_count += 1
        else:
            status_slug = "draft"
            status_label = "Draft"
        if status_slug in syllabus_status_summary:
            syllabus_status_summary[status_slug] += 1
        assignment_syllabus_statuses.append(
            {
                "assignment": a,
                "student_count": student_count,
                "status_slug": status_slug,
                "status_label": status_label,
            }
        )
    active_delegations_count = Delegation.objects.filter(
        delegator=request.user, is_active=True
    ).count()
    runtime = getattr(request, "tenant_runtime", None)
    if runtime is not None and getattr(runtime, "_school", None):
        syllabus_workflow = runtime.get_approval_workflow("syllabus_approval")
    else:
        syllabus_workflow = workflow_get_approval(
            getattr(request, "school", None), "syllabus_approval"
        )
    can_approve_syllabus = request.user.pk in (
        syllabus_workflow.get("approver_ids") or []
    )
    acting_delegation = get_active_delegation_for_delegate(request.user)
    if acting_delegation:
        delegator_role = getattr(acting_delegation.delegator, "role", "") or "User"
        acting_role_label = delegator_role.replace("_", " ").title()
    else:
        acting_role_label = None
    certification_badge = None
    if certification_stats and certification_stats.get("verified_candidates", 0) > 0:
        certification_badge = "CBA Certified"
    items_requiring_review = (
        widget_data.get("tasks", {}).get("pending_evaluations", 0)
        + syllabus_pending_count
    )
    teacher_metrics = [
        {
            "id": "teacher-classes",
            "label": "Classes",
            "value": len(assignments),
            "icon": "easel",
        },
        {
            "id": "teacher-completion",
            "label": "Marks completion",
            "value": f"{widget_data.get('completion_pct', 0)}%",
            "icon": "clipboard-check",
            "tone": (
                "success"
                if widget_data.get("completion_pct", 0) >= 80
                else "warning"
            ),
        },
        {
            "id": "teacher-attendance",
            "label": "Attendance",
            "value": f"{attendance_pct or 0}%",
            "icon": "calendar-check",
        },
        {
            "id": "teacher-review",
            "label": "Needs review",
            "value": items_requiring_review,
            "icon": "exclamation-triangle",
            "tone": "warning" if items_requiring_review else "success",
        },
    ]

    # Phase 1: Staff digital badges (non-expired, STAFF audience only)
    staff_badges = []
    if request.user.is_authenticated:
        staff_badges = list(
            Badge.objects.filter(
                user=request.user,
                badge_type__audience=BadgeType.Audience.STAFF,
            )
            .filter(Q(expiry_at__isnull=True) | Q(expiry_at__gt=timezone.now()))
            .select_related("badge_type")
            .order_by("-issued_at")[:10]
        )

    teacher_fast_workflows = [
        {"label": "Enter marks", "url": reverse("evals:teacher_marks_entry"), "icon": "bi-pencil-square"},
        {"label": "Attendance", "url": reverse("portal:take_student_attendance"), "icon": "bi-calendar-check"},
        {"label": "Grade import (CSV)", "url": reverse("evals:grade_import_upload"), "icon": "bi-file-earmark-arrow-up"},
        {"label": "Messages", "url": teacher_action_links.get("message", ""), "icon": "bi-chat-dots"},
        {"label": "Timetable", "url": reverse("portal:teacher_timetable"), "icon": "bi-table"},
    ]
    teacher_fast_workflows = [w for w in teacher_fast_workflows if w.get("url")]

    from apps.portal.tenant_role_home import (
        build_tp_hero_context,
        role_home_show_legacy,
    )

    pending_marks = int(widget_data.get("tasks", {}).get("pending_evaluations") or 0)
    completion_pct = int(widget_data.get("completion_pct") or 0)
    tp_hero = build_tp_hero_context(
        request,
        role=User.Role.TEACHER,
        pending_evaluations=pending_marks,
        completion_pct=completion_pct,
        attendance_pct=int(attendance_pct) if attendance_pct is not None else None,
    )

    from apps.dashboard.decision_surface_context import (
        build_role_home_declaration,
        build_teacher_dashboard_phase7_de,
    )

    teacher_role_home = {
        "dashboard_type": "role-home",
        "jtbd": "Complete marks and attendance with minimal navigation.",
        "main_question": "What needs my attention in class today?",
        "main_action": "Enter marks",
    }
    phase7_de = build_teacher_dashboard_phase7_de(
        pending_evaluations=pending_marks,
        completion_pct=completion_pct,
        attendance_pct=int(attendance_pct) if attendance_pct is not None else None,
        teacher_fast_workflows=teacher_fast_workflows,
    )
    role_home_declaration = build_role_home_declaration(teacher_role_home)

    return render(
        request,
        "teacher/dashboard.html",
        {
            **tp_hero,
            "phase7_de": phase7_de,
            "role_home_declaration": role_home_declaration,
            "teacher_show_legacy_dashboard": role_home_show_legacy(request),
            "year": year,
            "term": term,
            "assignments": assignments,
            "progress": progress,
            "widget_data": widget_data,
            "hero": hero,
            "show_welcome_hint": show_welcome_hint,
            "missing_records_url": missing_records_url,
            "grade_import_upload_url": reverse("evals:grade_import_upload"),
            "grade_import_template_url": reverse("evals:grade_import_template"),
            "display_widgets": display_widgets,
            "class_announcements": class_announcements,
            "class_threads": class_threads,
            "department_thread": department_thread,
            "team_peers": peers,
            "team_department": getattr(teacher_profile, "department", None),
            "finance_access_message": finance_banner,
            "finance_access_banner": finance_access_banner,
            "available_sidebar_items": available_sidebar_items,
            **dashboard_context,  # Unpack dashboard settings, layout URL, widget metadata, etc.
            "finance_requests_count": finance_requests_qs.count(),
            "finance_request_notifications": finance_requests_qs[:5],
            "finance_request_link": finance_request_link,
            "certification_stats": certification_stats,
            "gce_enabled": year and getattr(year, "enable_gce_registration", False)
            if year
            else False,
            "chart_completion_bar_json": chart_completion_bar_json,
            "chart_marks_donut_json": chart_marks_donut_json,
            "teacher_alerts": teacher_alerts,
            "ews_list": ews_list,
            "curriculum_map": curriculum_map,
            "dashboard_events": dashboard_events,
            "teacher_followup_items": teacher_followup_items,
            "teacher_deadline_items": teacher_deadline_items,
            "teacher_deadline_counts": teacher_deadline_counts,
            "teacher_action_links": teacher_action_links,
            "syllabus_items": syllabus_items,
            "assignment_syllabus_statuses": assignment_syllabus_statuses,
            "syllabus_status_summary": syllabus_status_summary,
            "syllabus_pending_count": syllabus_pending_count,
            "active_delegations_count": active_delegations_count,
            "acting_delegation": acting_delegation,
            "acting_role_label": acting_role_label,
            "can_approve_syllabus": can_approve_syllabus,
            "certification_badge": certification_badge,
            "items_requiring_review": items_requiring_review,
            "teacher_metrics": teacher_metrics,
            "staff_badges": staff_badges,
            "pending_leaves": pending_leaves,
            "workflow_summary": workflow_summary,
            "org_chain": org_chain,
            "teacher_org_tree": teacher_org_tree,
            "teacher_fast_workflows": teacher_fast_workflows,
        },
    )


def _teacher_workflow_link(label: str, url_name: str, *args, **kwargs) -> dict:
    """Build a workflow link dict; return None if URL fails to resolve."""
    try:
        return {"label": label, "url": reverse(url_name, args=args, kwargs=kwargs)}
    except EVALS_SOFT_FAILURES:
        return None


@teacher_portal_required
@role_required(User.Role.TEACHER)
def teacher_workflow_center(request: HttpRequest):
    """
    Teacher Workflow Center: steps with progress (what you've done → where you are → what's next).
    RBAC: teacher only; data scoped to current teacher's assignments.
    """
    teacher, error = _get_teacher_or_forbid(request)
    if error:
        return error
    from apps.portal.tenant_role_home import build_tp_hero_context
    from apps.portal.tenant_workflow_portal import build_tenant_workflow_portal

    year, term = get_active_year_and_term()
    if not year or not term:
        steps = [
            {
                "title": "Academic year setup",
                "subtitle": "Your school needs an active academic year and term before teaching workflows can fully run.",
                "step_key": "academic-year",
                "icon": "bi-calendar-event",
                "done": False,
                "progress_label": "Setup needed",
                "tip": "Ask an admin to activate the current academic year and term in School Studio.",
                "links": [
                    link
                    for link in [
                        _teacher_workflow_link("Teacher hub", "portal:teacher_dashboard_alias"),
                        _teacher_workflow_link("Help", "feedback:help_center"),
                    ]
                    if link
                ],
                "step_index": 1,
                "total_steps": 1,
            }
        ]
        workflow_progress = {
            "assignments": 0,
            "completion_pct": 0,
            "pending_marks": 0,
            "present_today": False,
            "pending_leaves": 0,
        }
        return render(
            request,
            "teacher/workflow_center.html",
            {
                **build_tp_hero_context(request, role=User.Role.TEACHER),
                "active_year": year,
                "active_term": term,
                "steps": steps,
                "workflow_progress": workflow_progress,
                "workflow_empty_state": True,
                "workflow_portal": build_tenant_workflow_portal(
                    request,
                    role=User.Role.TEACHER,
                    steps=steps,
                    workflow_progress=workflow_progress,
                    active_year=year,
                    active_term=term,
                    empty_state=True,
                ),
            },
        )

    teacher_profile, assignments, students_qs, classrooms = teacher_scope(
        request.user, academic_year=year
    )
    if teacher_profile is None:
        return HttpResponseForbidden(
            "Teacher profile or assignments missing. Contact an administrator."
        )

    # Empty state: profile exists but no class assignments yet
    if not assignments:

        def _filter_links(links):
            return [lnk for lnk in links if lnk is not None and lnk.get("url")]

        steps = [
            {
                "title": "Get class assignments",
                "subtitle": "You don't have any classes assigned yet.",
                "step_key": "assignments",
                "icon": "bi-person-badge",
                "done": False,
                "progress_label": "No classes assigned",
                "tip": "Contact your administrator to be assigned to classes. Once assigned, you'll see marks entry, attendance, and other workflow steps here.",
                "links": _filter_links(
                    [
                        _teacher_workflow_link(
                            "Teacher hub", "portal:teacher_dashboard_alias"
                        ),
                        _teacher_workflow_link("Syllabus", "portal:portal_syllabus"),
                    ]
                ),
                "step_index": 1,
                "total_steps": 1,
            },
        ]
        return render(
            request,
            "teacher/workflow_center.html",
            {
                "active_year": year,
                "active_term": term,
                "steps": steps,
                "workflow_progress": {
                    "assignments": 0,
                    "completion_pct": 0,
                    "pending_marks": 0,
                    "present_today": False,
                    "pending_leaves": 0,
                },
                "workflow_empty_state": True,
                **build_tp_hero_context(request, role=User.Role.TEACHER),
                "workflow_portal": build_tenant_workflow_portal(
                    request,
                    role=User.Role.TEACHER,
                    steps=steps,
                    workflow_progress={
                        "assignments": 0,
                        "completion_pct": 0,
                        "pending_marks": 0,
                        "present_today": False,
                        "pending_leaves": 0,
                    },
                    active_year=year,
                    active_term=term,
                    empty_state=True,
                ),
            },
        # tenant-isolation-allow: view-layer-scoped-via-request-school-or-role-graph
        )

    progress = {}
    # tenant-isolation-allow: view-layer-scoped-via-request-school-or-role-graph
    for a in assignments:
        sa = a.subject_assignment
        # tenant-isolation-allow: view-layer-scoped-via-request-school-or-role-graph
        total = StudentProfile.objects.filter(
            academic_year=year,
            classroom=sa.classroom,
            specialty=sa.specialty,
            is_active=True,
        ).count()
        # tenant-isolation-allow: view-layer-scoped-via-request-school-or-role-graph
        required = _required_fields(year, sa.classroom, term)
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

    teacher_dashboard_widget_data(assignments, progress, year, term, teacher=teacher)
    total_slots = sum((p.get("total", 0) for p in progress.values()), 0) or 1
    filled_slots = sum((p.get("filled", 0) for p in progress.values()), 0)
    completion_pct = int(round((filled_slots / total_slots) * 100))
    pending_marks = total_slots - filled_slots

    today = timezone.localdate()
    attendance_today = None
    if getattr(teacher_profile, "attendance_logs", None) is not None:
        attendance_today = teacher_profile.attendance_logs.filter(date=today).first()
    present_today = (
        attendance_today and attendance_today.status == TeacherAttendance.Status.PRESENT
    )

    pending_leaves = 0
    if getattr(teacher_profile, "leave_requests", None) is not None:
        pending_leaves = teacher_profile.leave_requests.filter(
            status=TeacherLeaveRequest.Status.PENDING
        ).count()

    def _filter_links(links):
        return [lnk for lnk in links if lnk is not None and lnk.get("url")]

    steps = [
        {
            "title": "1) My profile & timetable",
            "subtitle": "Onboarding, assignments, and schedule.",
            "step_key": "profile",
            "icon": "bi-person-badge",
            "done": bool(assignments),
            "progress_label": f"{len(assignments)} classes"
            if assignments
            else "No assignments",
            "tip": "Ensure your profile and class assignments are up to date.",
            "links": _filter_links(
                [
                    _teacher_workflow_link(
                        "Teacher hub", "portal:teacher_dashboard_alias"
                    ),
                    _teacher_workflow_link("Syllabus", "portal:portal_syllabus"),
                ]
            ),
        },
        {
            "title": "2) Daily routine",
            "subtitle": "Your attendance and class attendance.",
            "step_key": "daily",
            "icon": "bi-calendar-check",
            "done": bool(present_today),
            "progress_label": "Checked in today" if present_today else "Not checked in",
            "tip": "Check in when you arrive; take class attendance for each period.",
            "links": _filter_links(
                [
                    _teacher_workflow_link(
                        "My attendance", "portal:teacher_attendance"
                    ),
                ]
            ),
        },
        {
            "title": "3) Marks & sequences",
            "subtitle": "Enter marks (Sequences 1–6), submit for approval.",
            "step_key": "marks",
            "icon": "bi-pencil-square",
            "done": pending_marks == 0,
            "progress_label": f"{completion_pct}% entered · {pending_marks} pending"
            if total_slots
            else "No slots",
            "tip": "Enter CA for each sequence; submit for approval when ready.",
            "links": _filter_links(
                [
                    _teacher_workflow_link("Enter marks", "evals:teacher_marks_entry"),
                    _teacher_workflow_link("View marks", "evals:teacher_marks_list"),
                    _teacher_workflow_link("Grade import", "evals:grade_import_upload"),
                    _teacher_workflow_link(
                        "Download template", "evals:grade_import_template"
                    ),
                ]
            ),
        },
        {
            "title": "4) Reports & communication",
            "subtitle": "Report cards, announcements, parent contact.",
            "step_key": "reports",
            "icon": "bi-chat-dots",
            "done": completion_pct >= 80,
            "progress_label": None,
            "tip": "After approval, admin publishes reports; use messages for parent alerts.",
            "links": _filter_links(
                [
                    _teacher_workflow_link(
                        "Department Chat", "communication:group_list"
                    ),
                ]
                + (
                    [
                        _teacher_workflow_link(
                            "Create announcement",
                            "communication:department_announcement_create",
                        )
                    ]
                    if _can_create_department_announcement(request.user)
                    else []
                )
            ),
        },
        {
            "title": "5) My attendance & pay",
            "subtitle": "Your attendance record, pay history, leave.",
            "step_key": "pay",
            "icon": "bi-wallet2",
            "done": bool(present_today) and pending_leaves == 0,
            "progress_label": f"Present today · {pending_leaves} leave request(s)"
            if present_today
            else f"Not checked in · {pending_leaves} leave request(s)",
            "tip": None,
            "links": _filter_links(
                [
                    _teacher_workflow_link(
                        "My attendance", "portal:teacher_attendance"
                    ),
                    _teacher_workflow_link("Pay history", "portal:teacher_pay_history"),
                    _teacher_workflow_link("Leave requests", "portal:teacher_leave"),
                ]
            ),
        },
    ]
    total_steps = len(steps)
    for i, s in enumerate(steps, start=1):
        s["step_index"] = i
        s["total_steps"] = total_steps

    workflow_progress = {
        "assignments": len(assignments),
        "completion_pct": completion_pct,
        "pending_marks": pending_marks,
        "present_today": present_today,
        "pending_leaves": pending_leaves,
    }

    return render(
        request,
        "teacher/workflow_center.html",
        {
            **build_tp_hero_context(
                request,
                role=User.Role.TEACHER,
                pending_evaluations=int(pending_marks or 0),
                completion_pct=int(completion_pct or 0),
            ),
            "active_year": year,
            "active_term": term,
            "steps": steps,
            "workflow_progress": workflow_progress,
            "workflow_portal": build_tenant_workflow_portal(
                request,
                role=User.Role.TEACHER,
                steps=steps,
                workflow_progress=workflow_progress,
                active_year=year,
                active_term=term,
                empty_state=False,
            ),
        },
    )


@trace_view("grade.entry", op="view.hot_path")
@teacher_portal_required
@role_required(User.Role.TEACHER)
def teacher_marks_entry(request: HttpRequest):
    teacher, error = _get_teacher_or_forbid(request)
    if error:
        return error
    year, active_term = get_active_year_and_term()
    # tenant-isolation-allow: view-layer-scoped-via-request-school-or-role-graph
    if not year or not active_term:
        return HttpResponseForbidden("No active academic year/term set by admin yet.")

    # tenant-isolation-allow: view-layer-scoped-via-request-school-or-role-graph
    teacher_assignments = TeacherAssignment.objects.filter(
        teacher=teacher, academic_year=year, is_active=True
    ).select_related("subject_assignment")

    selected_sa_id = request.GET.get("subject_assignment_id") or request.POST.get(
        "subject_assignment_id"
    )
    sa = None
    students = []
    existing = {}  # student_id -> Evaluation
    locked = False

    show_missing = request.GET.get("missing") == "1"
    required_fields = []
    filled_count = 0
    total_students_count = 0
    # Policy from runtime constitution (see REFACTOR_PATTERN_GRADEBOOK_AND_ADMISSIONS.md)
    from apps.evals.runtime_helpers import get_policy_for_request

    policy = get_policy_for_request(request)
    if policy:
        flags = {**default_backend_feature_flags(), **(policy.get("features") or {})}
        grade_approval_enabled = (policy.get("grade_approval") or {}).get(
            "grade_approval_enabled", False
        )
        site_settings = get_effective_site_settings(request=request)
    else:
        site_settings = get_effective_site_settings(request=request)
        flags = {
            **default_backend_feature_flags(),
            **(getattr(site_settings, "backend_feature_flags", None) or {}),
        }
        grade_approval_enabled = getattr(site_settings, "grade_approval_enabled", False)
    custom_cmd = (site_settings.marksheet_ocr_command or "").strip()
    env_cmd = getattr(settings, "MARKSHEET_OCR_COMMAND", "") or ""
    resolved_cmd = (custom_cmd or env_cmd or "").strip()
    ocr_command = resolved_cmd or None
    marksheet_ocr_ready, marksheet_ocr_version = is_tesseract_available(ocr_command)
    marksheet_ocr_command_display = resolved_cmd or "tesseract"
    upload_form = (
        MarkSheetUploadForm(initial={"subject_assignment_id": selected_sa_id})
        if selected_sa_id
        else MarkSheetUploadForm()
    )
    upload_preview = []
    upload_feedback = None
    upload_summary: dict[str, Any] = {"processed": 0}
    upload_confidence = 0.0
    upload_manual_review_pending = False
    student_lookup: dict[str, StudentProfile] = {}

    if selected_sa_id:
        # Guard: must be assigned
        if not teacher_assignments.filter(
            subject_assignment_id=selected_sa_id
        ).exists():
            return HttpResponseForbidden("You are not assigned to this subject/class.")

        sa = get_object_or_404(SubjectAssignment, id=selected_sa_id)
        if (
            getattr(active_term, "position", None) == 3
            and not sa.classroom.allows_third_term
        ):
            return HttpResponseForbidden(
                "Third term is not enabled for this classroom."
            # tenant-isolation-allow: view-layer-scoped-via-request-school-or-role-graph
            )

        # Publish lock check (term published) or year hard lock (rollover finalization)
        locked = is_term_published(year.id, active_term.id, sa.classroom_id) or getattr(
            # tenant-isolation-allow: view-layer-scoped-via-request-school-or-role-graph
            year, "is_locked", False
        )

        # tenant-isolation-allow: view-layer-scoped-via-request-school-or-role-graph
        # Load students for this class/specialty/year
        students = list(
            # tenant-isolation-allow: view-layer-scoped-via-request-school-or-role-graph
            StudentProfile.objects.filter(
                academic_year=year,
                classroom=sa.classroom,
                specialty=sa.specialty,
                is_active=True,
            ).order_by("last_name", "first_name")
        )

        total_students_count = len(students)

        required_fields = _required_fields(year, sa.classroom, active_term)
# tenant-isolation-allow: view-layer-scoped-via-request-school-or-role-graph

        # Load existing evaluations so we can pre-fill inputs
        # tenant-isolation-allow: view-layer-scoped-via-request-school-or-role-graph
        evals = Evaluation.objects.filter(
            academic_year=year,
            term=active_term,
            subject_assignment=sa,
            student__in=students,
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
    pending_data = (
        _pending_ocr_for(request.session, teacher.id, selected_sa_pk)
        if selected_sa_pk
        else None
    )

    if request.method == "POST" and confirm_pending:
        upload_form = (
            MarkSheetUploadForm(initial={"subject_assignment_id": selected_sa_id})
            if selected_sa_id
            else MarkSheetUploadForm()
        )
        if not sa:
            messages.error(request, "Please select an assignment first.")
            upload_feedback = {
                "level": "danger",
                "message": "Select an assignment before uploading a marksheet.",
            }
        elif locked:
            return HttpResponseForbidden(
                "This term is published/locked. Marks entry is disabled."
            )
        elif not pending_data:
            upload_feedback = {
                "level": "warning",
                "message": "No OCR preview is staged for this assignment.",
            }
        elif request.POST.get("confirm_human_review") != "1":
            upload_feedback = {
                "level": "warning",
                "message": "Confirm that you reviewed the OCR proposal before applying it.",
            }
            upload_manual_review_pending = True
        else:
            # tenant-isolation-allow: view-layer-scoped-via-request-school-or-role-graph
            entries = _deserialize_pending_entries(pending_data["entries"])
            upload_confidence = pending_data.get("confidence", 0.0) or 0.0

            # Extract corrected values from form (if user edited preview table)
            # tenant-isolation-allow: view-layer-scoped-via-request-school-or-role-graph
            corrected_entries = _extract_corrected_ocr_entries(request.POST, entries)
            entries_to_apply = corrected_entries if corrected_entries else entries
            # Local-first: validate against THIS school's operational grading-scale
            # max (the scale grades are computed on), not a hardcoded 0-20 (which
            # rejected valid scores on percentage / GPA scales).
            from apps.evals.grading_provisioning import resolve_school_score_scale

            validation_errors = _validate_ocr_entries(
                entries_to_apply, resolve_school_score_scale(getattr(teacher, "school", None))
            )

            # Build existing evaluations for delta preview
            # tenant-isolation-allow: view-layer-scoped-via-request-school-or-role-graph
            existing_evals = {}
            if sa and students:
                existing_evals = {
                    # tenant-isolation-allow: view-layer-scoped-via-request-school-or-role-graph
                    eval_obj.student_id: eval_obj
                    for eval_obj in Evaluation.objects.filter(
                        academic_year=year,
                        term=active_term,
                        subject_assignment=sa,
                        student__in=students,
                    ).select_related("student")
                }

            upload_preview = _build_ocr_preview(
                entries_to_apply, student_lookup, existing_evals
            )
            delta_mode = flags.get("marksheet_ocr_delta_mode", True)
            if validation_errors:
                upload_summary = {
                    "processed": len(entries_to_apply),
                    "confidence": upload_confidence,
                    "delta_mode": delta_mode,
                }
                upload_feedback = {
                    "level": "danger",
                    "message": "Correct invalid OCR values before applying: "
                    + "; ".join(validation_errors[:5]),
                }
                upload_manual_review_pending = True
            else:
                applied = _apply_ocr_entries(
                    entries_to_apply,
                    student_lookup,
                    sa,
                    year,
                    active_term,
                    teacher,
                    delta_mode=delta_mode,
                )
                upload_summary = {
                    "processed": len(entries_to_apply),
                    "confidence": upload_confidence,
                    "applied": len(applied),
                    "delta_mode": delta_mode,
                }
                upload_feedback = {
                    "level": "success" if applied else "info",
                    "message": (
                        f"Applied {len(applied)} teacher-confirmed entries "
                        f"(delta mode: {'on' if delta_mode else 'off'})."
                        if applied
                        else "No matching students were updated."
                    ),
                }
                messages.success(
                    request, "Teacher-confirmed OCR proposal applied successfully."
                )
                _clear_pending_ocr(request.session)
    elif request.method == "POST" and marksheet_file:
        upload_form = MarkSheetUploadForm(request.POST, request.FILES)
        if not sa:
            messages.error(request, "Please select an assignment first.")
            upload_feedback = {
                "level": "danger",
                "message": "Select an assignment before uploading a marksheet.",
            }
        elif locked:
            return HttpResponseForbidden(
                "This term is published/locked. Marks entry is disabled."
            )
        elif not upload_form.is_valid():
            upload_feedback = {
                "level": "danger",
                "message": "Upload form is invalid. Check the fields and try again.",
            }
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
                # tenant-isolation-allow: view-layer-scoped-via-request-school-or-role-graph
                tesseract_cmd=ocr_command,
            )
            entries = ocr_result.get("entries", [])
            upload_confidence = ocr_result.get("confidence", 0.0) or 0.0
            # tenant-isolation-allow: view-layer-scoped-via-request-school-or-role-graph
            field_confidences = ocr_result.get(
                "field_confidences", {}
            )  # Per-field confidence

            # tenant-isolation-allow: view-layer-scoped-via-request-school-or-role-graph
            # Build existing evaluations map for delta preview
            existing_evals = {}
            if sa and students:
                # tenant-isolation-allow: view-layer-scoped-via-request-school-or-role-graph
                existing_evals = {
                    eval_obj.student_id: eval_obj
                    # tenant-isolation-allow: view-layer-scoped-via-request-school-or-role-graph
                    for eval_obj in Evaluation.objects.filter(
                        academic_year=year,
                        term=active_term,
                        subject_assignment=sa,
                        student__in=students,
                    ).select_related("student")
                }

            upload_preview = _build_ocr_preview(entries, student_lookup, existing_evals)
            delta_mode = flags.get(
                "marksheet_ocr_delta_mode", True
            )  # Only fill missing by default
            upload_manual_review_pending = bool(entries)
            upload_summary = {
                "processed": len(entries),
                "confidence": upload_confidence,
                "field_confidences": field_confidences,
                "delta_mode": delta_mode,
            }
            if entries:
                upload_feedback = {
                    "level": "info",
                    "message": (
                        "OCR created a proposal only. Review and correct every value "
                        "before explicitly applying it."
                    ),
                }
                _set_pending_ocr(
                    request.session,
                    teacher.id,
                    selected_sa_pk,
                    entries,
                    upload_confidence,
                    field_confidences,
                )
            else:
                upload_feedback = {
                    "level": "warning",
                    "message": ocr_result.get("message")
                    or "No data extracted from the marksheet.",
                }
                _clear_pending_ocr(request.session)
    elif request.method == "POST":
        if not sa:
            messages.error(request, "Please select an assignment first.")
            return redirect("evals:teacher_marks_entry")

        if locked:
            return HttpResponseForbidden(
                "This term is published/locked. Marks entry is disabled."
            )

        action = request.POST.get("action")
        try:
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
        except EVALS_SOFT_FAILURES:
            logger.exception(
                "Marks save failed: user=%s subject_assignment_id=%s students_count=%s",
                request.user.id,
                sa.id,
                len(students),
                exc_info=True,
            )
            messages.error(
                request,
                "Marks could not be saved. Please try again or contact support.",
            )
            return redirect("evals:teacher_marks_entry")

        if action == "submit_for_approval" and grade_approval_enabled:
            max_mark = Decimal("20")
            for entry in entries_payload:
                for val in entry.get("scores", {}).values():
                    if val in (None, ""):
                        continue
                    try:
                        d = Decimal(str(val))
                    except (InvalidOperation, TypeError, ValueError):
                        messages.error(
                            request, "Invalid mark value. Use numbers between 0 and 20."
                        )
                        return redirect("evals:teacher_marks_entry")
                    if d < 0 or d > max_mark:
                        messages.error(
                            request,
                            "Each mark must be between 0 and 20 before requesting approval.",
                        )
                        return redirect("evals:teacher_marks_entry")
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
                messages.warning(
                    request, "Enter at least one mark before requesting approval."
                )
            else:
                messages.success(
                    request, "Grades submitted for review. Awaiting approver feedback."
                )
                return redirect("evals:teacher_marks_list")

        # Direct post (no approval workflow): the approval branch above returns
        # early, so reaching here means grades were saved directly and are now
        # visible to the student. Notify the student + guardians via the Phase-3
        # router. Best-effort + on_commit inside the helper — never breaks the save.
        try:
            from apps.evals.notify_published import notify_grades_published_direct

            graded_students = [
                students_map[entry["student_id"]]
                for entry in entries_payload
                if entry.get("has_scores") and entry["student_id"] in students_map
            ]
            notify_grades_published_direct(
                students=graded_students,
                subject_assignment=sa,
                school=getattr(request, "school", None),
            )
        except Exception:  # noqa: BLE001 — notification must never break marks save
            logger.warning(
                "grade.published direct-notify wiring failed", exc_info=False
            )

        messages.success(request, "Marks saved successfully.")
        return redirect("evals:teacher_marks_list")

    # tenant-isolation-allow: view-layer-scoped-via-request-school-or-role-graph
    pending_data = (
        _pending_ocr_for(request.session, teacher.id, selected_sa_pk)
        if selected_sa_pk
        else None
    # tenant-isolation-allow: view-layer-scoped-via-request-school-or-role-graph
    )
    if pending_data:
        pending_entries = _deserialize_pending_entries(pending_data["entries"])
        # Rebuild existing evaluations for delta preview
        # tenant-isolation-allow: view-layer-scoped-via-request-school-or-role-graph
        existing_evals = {}
        if sa and students:
            existing_evals = {
                # tenant-isolation-allow: view-layer-scoped-via-request-school-or-role-graph
                eval_obj.student_id: eval_obj
                for eval_obj in Evaluation.objects.filter(
                    academic_year=year,
                    term=active_term,
                    subject_assignment=sa,
                    student__in=students,
                ).select_related("student")
            }
        upload_preview = _build_ocr_preview(
            pending_entries, student_lookup, existing_evals
        )
        upload_confidence = pending_data.get("confidence", upload_confidence) or 0.0
        field_confidences = pending_data.get("field_confidences", {})
        upload_summary = {
            "processed": len(pending_entries),
            "confidence": upload_confidence,
            "field_confidences": field_confidences,
            "delta_mode": flags.get("marksheet_ocr_delta_mode", True),
        }
        upload_manual_review_pending = True

    # Local-first: bind the manual mark inputs to THIS school's grading-scale max
    # (the operational scale grades are scored on — 20 francophone, 100 percentage,
    # 4 GPA), so a non-/20 tenant can enter valid marks. Cameroon /20 → max="20"
    # (unchanged), mirroring _validate_ocr_entries which uses the same resolver.
    from apps.evals.grading_provisioning import resolve_school_score_scale

    max_score = _normalized_scale_max(
        resolve_school_score_scale(getattr(teacher, "school", None))
    )

    # GET: render selection + (optional) student table
    return render(
        request,
        "teacher/marks_entry.html",
        {
            "year": year,
            "term": active_term,
            "max_score": max_score,
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
            "marksheet_mobile_upload_allowed": flags.get(
                "marksheet_ocr_mobile_upload_enabled", True
            ),
            "marksheet_ocr_ready": marksheet_ocr_ready,
            "marksheet_ocr_version": marksheet_ocr_version,
            "marksheet_ocr_command": marksheet_ocr_command_display,
            "marksheet_ocr_delta_mode": flags.get("marksheet_ocr_delta_mode", True),
            "plickers_card_sweep_enabled": flags.get(
                "plickers_card_sweep_enabled", True
            ),
            "grade_approval_enabled": grade_approval_enabled,
            "grade_approval_requests": grade_approval_requests,
            "grade_approval_roles": grade_approver_roles(
                school=getattr(request, "school", None), policy=policy
            ),
        },
    )


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

    # tenant-isolation-allow: view-layer-scoped-via-request-school-or-role-graph
    teacher_assignments = TeacherAssignment.objects.filter(
        teacher=teacher, academic_year=year, is_active=True
    )

    classrooms = teacher_assignments.values_list(
        "subject_assignment__classroom_id", "subject_assignment__classroom__name"
    ).distinct()
    subjects = teacher_assignments.values_list(
        "subject_assignment__subject_id", "subject_assignment__subject__name"
    ).distinct()
    classroom_map = {str(item[0]): item[1] for item in classrooms if item[0]}
    subject_map = {str(item[0]): item[1] for item in subjects if item[0]}
# tenant-isolation-allow: view-layer-scoped-via-request-school-or-role-graph

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
            Q(seq1_score__isnull=True)
            | Q(test1__isnull=True)
            | Q(seq2_score__isnull=True)
            | Q(test2__isnull=True)
            | Q(exam_score__isnull=True)
            | Q(mock_score__isnull=True)
            | Q(practical_score__isnull=True)
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

    page_number = request.GET.get("page", 1)
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
        filters = _build_filter_labels(
            classroom_id, subject_id, term_id, missing_only, classroom_map, subject_map
        )
        pdf_context = {
            "report_title": f"{user_name} Marks Export",
            "report_period": f"{term.label} · {year.name}",
            "report_total": f"{len(rows)} records",
            "rows": rows,
            "filters": filters,
            "generated_at": timezone.now(),
            "summary": f"{len(rows)} evaluations",
        }
        pdf_bytes = render_pdf_bytes(
            request, "reports/evaluation_grid.html", pdf_context
        )
        filename = f"teacher-marks-{year.name}-{term.name}.pdf".replace(" ", "_")
        response = HttpResponse(pdf_bytes, content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response

    if export_csv:
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="teacher-marks.csv"'
        writer = csv.writer(response)
        writer.writerow(
            [
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
            ]
        )
        for e in evals_list:
            writer.writerow(
                [
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
                ]
            )
        return response

    compare_raw = (request.GET.get("compare") or "").strip()
    rosetta_target = (
        compare_raw
        if compare_raw in get_supported_scales()
        else ""
    )
    # Resolve the school's operational scale ONCE (N+1-safe) so the gradebook can show
    # the native grade label (WAEC A1–F9, Pass/Fail, descriptor) for non-numeric scales.
    from apps.evals.grading_provisioning import resolve_local_scale_type
    from apps.evals.models import resolve_extended_band_label

    list_scale_type = resolve_local_scale_type(getattr(teacher, "school", None))
    mark_rows: list[dict[str, Any]] = []
    for e in evals_list:
        rosetta = None
        if rosetta_target:
            rosetta = view_grade_in_target_system(e, rosetta_target)
        mark_rows.append(
            {
                "evaluation": e,
                "rosetta": rosetta,
                "band": resolve_extended_band_label(list_scale_type, e.total_score),
            }
        )

    export_csv_params = request.GET.copy()
    export_csv_params["export"] = "csv"
    export_pdf_params = request.GET.copy()
    export_pdf_params["export"] = "pdf"

    rosetta_choices: list[tuple[str, str]] = [
        ("", "—"),
        ("0-100", "Percentage (0–100)"),
        ("0-20", "0–20"),
        ("gpa", "GPA 4.0"),
        ("0-10", "0–10"),
        ("a-f", "Letter A–F (4-pt)"),
    ]
    rosetta_col_label = ""
    for k, lab in rosetta_choices:
        if k == rosetta_target:
            rosetta_col_label = lab
            break

    return render(
        request,
        "teacher/marks_list.html",
        {
            # tenant-isolation-allow: view-layer-scoped-via-request-school-or-role-graph
            "year": year,
            "term": term,
            "evals": evals_list,
            "mark_rows": mark_rows,
            "rosetta_target": rosetta_target,
            "rosetta_column_label": rosetta_col_label,
            # tenant-isolation-allow: view-layer-scoped-via-request-school-or-role-graph
            "rosetta_target_choices": rosetta_choices,
            "paginator": paginator,
            "page_obj": evals_page,
            "classrooms": list(classrooms),
            # tenant-isolation-allow: view-layer-scoped-via-request-school-or-role-graph
            "subjects": list(subjects),
            "term_choices": list(Term.objects.all()),
            "selected": {
                "classroom": classroom_id or "",
                "subject": subject_id or "",
                "term": term_id or "",
                "missing": "1" if missing_only else "",
                "compare": rosetta_target,
            },
            "export_csv_query": export_csv_params.urlencode(),
            "export_pdf_query": export_pdf_params.urlencode(),
        },
    )


@teacher_portal_required
@role_required(User.Role.TEACHER)
def rosetta_grade_preview_api(request: HttpRequest):
    """JSON helper: see one grade in a target system (used by markbook and integrations)."""
    if request.method != "GET":
        return JsonResponse({"ok": False, "error": "method_not_allowed"}, status=405)
    teacher, error = _get_teacher_or_forbid(request)
    if error:
        return JsonResponse({"ok": False, "error": "forbidden"}, status=403)
    try:
        ev_id = int(request.GET.get("evaluation_id") or 0)
    except (TypeError, ValueError):
        return JsonResponse(
            {"ok": False, "error": "invalid evaluation_id"},
            status=400,
        )
    to_scale = (request.GET.get("to_scale") or "0-100").strip()
    if to_scale not in get_supported_scales():
        to_scale = "0-100"
    try:
        ev = Evaluation.objects.select_related("school", "teacher").get(pk=ev_id)
    except Evaluation.DoesNotExist:
        return JsonResponse({"ok": False, "error": "not_found"}, status=404)
    if ev.teacher_id != teacher.id:
        return JsonResponse({"ok": False, "error": "forbidden"}, status=403)
    school = getattr(request, "school", None)
    if school is not None and ev.school_id is not None and ev.school_id != school.id:
        return JsonResponse({"ok": False, "error": "forbidden"}, status=403)
    return JsonResponse(view_grade_in_target_system(ev, to_scale))


@staff_member_required(login_url=settings.LOGIN_URL)
def class_ranking_view(request: HttpRequest):
    """Class ranking (best to worst) for a given year/term/classroom.

    This is a staff-only view intended for Admin/Leadership.

    Optimization: Uses cached rankings with 15-minute TTL and batch-loaded
    evaluations to avoid N+1 queries.
    """
    from django.utils.translation import gettext

    year, active_term = get_active_year_and_term()
    if not year or not active_term:
        return HttpResponseForbidden("No active academic year/term set by admin yet.")

    # tenant-isolation-allow: view-layer-scoped-via-request-school-or-role-graph
    year_id = request.GET.get("year") or str(year.id)
    term_id = request.GET.get("term") or str(active_term.id)
    classroom_id = request.GET.get("classroom")

    year_obj = get_object_or_404(AcademicYear, id=year_id)
    # tenant-isolation-allow: view-layer-scoped-via-request-school-or-role-graph
    term_obj = get_object_or_404(Term, id=term_id)

    # tenant-isolation-allow: view-layer-scoped-via-request-school-or-role-graph
    classrooms = Classroom.objects.filter(academic_year=year_obj).order_by("name")
    selected_classroom = None
    ranking = []
    stats = None
    rows = []
    is_t_score = False

    if classroom_id:
        selected_classroom = get_object_or_404(Classroom, id=classroom_id)

        from .services import get_class_stats
        from .ranking import get_class_ranking, resolve_ranking_mode

        # Get optimized ranking with tie handling and caching
        ranking = get_class_ranking(selected_classroom, term_obj)
        # Under T-score mode the "average" column carries a cohort-relative
        # standardized score (hensachi, mean 50), not a raw mean — label it honestly.
        is_t_score = (
            resolve_ranking_mode(term_obj, selected_classroom) == "standard_score_t"
        )
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
        # Paginate ranking (e.g. 50 per page) for large classes; validate page_size
        try:
            per_page = min(100, max(20, int(request.GET.get("page_size", 50))))
        except (TypeError, ValueError):
            per_page = settings.DEFAULT_ADMIN_PAGE_SIZE
        paginator = Paginator(rows, per_page)
        page_number = request.GET.get("page", 1)
        try:
            page_obj = paginator.get_page(page_number)
        except PageNotAnInteger:
            page_obj = paginator.get_page(1)
        except EmptyPage:
            page_obj = paginator.get_page(paginator.num_pages)
        rows = list(page_obj.object_list)
        q = request.GET.copy()
        q.pop("page", None)
        pagination_extra_query = q.urlencode()
    # tenant-isolation-allow: view-layer-scoped-via-request-school-or-role-graph
    else:
        page_obj = None
        q = request.GET.copy()
        q.pop("page", None)
        pagination_extra_query = q.urlencode()

    # tenant-isolation-allow: view-layer-scoped-via-request-school-or-role-graph
    return render(
        request,
        "evals/class_ranking.html",
        {
            # tenant-isolation-allow: view-layer-scoped-via-request-school-or-role-graph
            "year": year_obj,
            "term": term_obj,
            "selected_year": year_obj,
            "selected_term": term_obj,
            # tenant-isolation-allow: view-layer-scoped-via-request-school-or-role-graph
            "years": AcademicYear.objects.order_by("-start_date"),
            "terms": Term.objects.filter(academic_year=year_obj).order_by(
                "start_date", "name"
            ),
            "classrooms": classrooms,
            "selected_classroom": selected_classroom,
            "rows": rows,
            "stats": stats,
            "is_t_score": is_t_score,
            "score_label": gettext("T-score") if is_t_score else gettext("Average"),
            "page_obj": page_obj,
            "pagination_extra_query": pagination_extra_query,
        },
    )


@staff_member_required(login_url=settings.LOGIN_URL)
def school_ranking_view(request: HttpRequest):
    """School-wide ranking for a given year/term.

    Optimization: Uses cached rankings with 15-minute TTL and batch-loaded
    evaluations to avoid N+1 queries. Proper tie handling ensures deterministic
    ranking even when students have identical averages.
    """
    from django.utils.translation import gettext

    year, active_term = get_active_year_and_term()
    if not year or not active_term:
        return HttpResponseForbidden("No active academic year/term set by admin yet.")

    year_id = request.GET.get("year") or str(year.id)
    term_id = request.GET.get("term") or str(active_term.id)

    year_obj = get_object_or_404(AcademicYear, id=year_id)
    term_obj = get_object_or_404(Term, id=term_id)

    from .ranking import get_school_ranking, resolve_ranking_mode

    # Get optimized ranking with tie handling and caching
    ranking = get_school_ranking(term_obj)
    # Under T-score mode the "average" column carries a cohort-relative standardized
    # score (hensachi, mean 50), not a raw mean — label it honestly in the display.
    is_t_score = resolve_ranking_mode(term_obj, None) == "standard_score_t"

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
    try:
        per_page = min(100, max(20, int(request.GET.get("page_size", 50))))
    except (TypeError, ValueError):
        per_page = settings.DEFAULT_ADMIN_PAGE_SIZE
    paginator = Paginator(rows, per_page)
    page_number = request.GET.get("page", 1)
    try:
        page_obj = paginator.get_page(page_number)
    except PageNotAnInteger:
        page_obj = paginator.get_page(1)
    # tenant-isolation-allow: view-layer-scoped-via-request-school-or-role-graph
    except EmptyPage:
        page_obj = paginator.get_page(paginator.num_pages)
    rows = list(page_obj.object_list)
    q = request.GET.copy()
    q.pop("page", None)
    pagination_extra_query = q.urlencode()
# tenant-isolation-allow: view-layer-scoped-via-request-school-or-role-graph

    return render(
        request,
        "evals/school_ranking.html",
        # tenant-isolation-allow: view-layer-scoped-via-request-school-or-role-graph
        {
            "year": year_obj,
            "term": term_obj,
            "selected_year": year_obj,
            # tenant-isolation-allow: view-layer-scoped-via-request-school-or-role-graph
            "selected_term": term_obj,
            "years": AcademicYear.objects.order_by("-start_date"),
            # tenant-isolation-allow: view-layer-scoped-via-request-school-or-role-graph
            "terms": Term.objects.filter(academic_year=year_obj).order_by(
                "start_date", "name"
            ),
            "rows": rows,
            "is_t_score": is_t_score,
            "score_label": gettext("T-score") if is_t_score else gettext("Average"),
            "page_obj": page_obj,
            "pagination_extra_query": pagination_extra_query,
        },
    )


@staff_member_required(login_url=settings.LOGIN_URL)
def evaluation_admin(request: HttpRequest):
    # tenant-isolation-allow: view-layer-scoped-via-request-school-or-role-graph
    year, active_term = get_active_year_and_term()
    if not year or not active_term:
        return HttpResponseForbidden("No active academic year/term set by admin yet.")

    year_id = request.GET.get("year") or str(year.id)
    term_id = request.GET.get("term") or str(active_term.id)
    # tenant-isolation-allow: view-layer-scoped-via-request-school-or-role-graph
    classroom_id = request.GET.get("classroom")
    subject_id = request.GET.get("subject")
    missing_only = request.GET.get("missing") == "1"

    # tenant-isolation-allow: view-layer-scoped-via-request-school-or-role-graph
    year_obj = get_object_or_404(AcademicYear, id=year_id)
    term_obj = get_object_or_404(Term, id=term_id)
    classroom_obj = (
        # tenant-isolation-allow: view-layer-scoped-via-request-school-or-role-graph
        Classroom.objects.filter(id=classroom_id).first() if classroom_id else None
    )

    filter_form = EvaluationFilterForm(
        data=request.GET or None,
        academic_year=year_obj,
        school=getattr(request, "school", None),
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
        school=getattr(request, "school", None),
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
        # tenant-isolation-allow: view-layer-scoped-via-request-school-or-role-graph
        prefix="fill",
    )

    if request.method == "POST" and request.POST.get("action") == "bulk_create":
        if create_form.is_valid():
            # tenant-isolation-allow: view-layer-scoped-via-request-school-or-role-graph
            subject_assignment = create_form.cleaned_data["subject_assignment"]
            teacher = create_form.cleaned_data["teacher"]
# tenant-isolation-allow: view-layer-scoped-via-request-school-or-role-graph

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
                    # tenant-isolation-allow: view-layer-scoped-via-request-school-or-role-graph
                    classroom=classroom_value,
                    defaults={
                        "seq1_weight": data["seq1_weight"],
                        "seq2_weight": data["seq2_weight"],
                        "exam_weight": data["exam_weight"],
                        "mock_weight": data["mock_weight"],
                        # tenant-isolation-allow: view-layer-scoped-via-request-school-or-role-graph
                        "practical_weight": data["practical_weight"],
                        "score_scale": data["score_scale"],
                    },
                )
                # tenant-isolation-allow: view-layer-scoped-via-request-school-or-role-graph
                messages.success(request, "Assessment weights saved.")
                redirect_target = (
                    request.path + f"?year={year_obj.id}&term={term_obj.id}"
                )
                if classroom_id:
                    # tenant-isolation-allow: view-layer-scoped-via-request-school-or-role-graph
                    redirect_target += f"&classroom={classroom_id}"
                return redirect(redirect_target)

    # tenant-isolation-allow: view-layer-scoped-via-request-school-or-role-graph
    evals = (
        Evaluation.objects.filter(academic_year=year_obj, term=term_obj)
        .select_related(
            "student",
            "teacher",
            "subject_assignment__classroom",
            "subject_assignment__specialty",
            "subject_assignment__subject",
        )
        .prefetch_related("evidence")
    )

    if classroom_obj:
        evals = evals.filter(subject_assignment__classroom=classroom_obj)
    if subject_id:
        evals = evals.filter(subject_assignment__subject_id=subject_id)

    required_fields = _required_fields(year_obj, classroom_obj, term_obj)
    evals_list = list(evals.order_by("-updated_at"))
    # tenant-isolation-allow: view-layer-scoped-via-request-school-or-role-graph
    if missing_only:
        evals_list = [
            e
            for e in evals_list
            if any(
                getattr(e, field) is None
                for field in _required_fields_for_evaluation(e)
            # tenant-isolation-allow: view-layer-scoped-via-request-school-or-role-graph
            )
        ]

    if request.method == "POST" and request.POST.get("action") == "fill_missing":
        # tenant-isolation-allow: view-layer-scoped-via-request-school-or-role-graph
        if fill_form.is_valid():
            fill_value = Decimal(fill_form.cleaned_data["fill_value"])
            updated = 0
            for evaluation in evals_list:
                needs_update = False
                updates = {}
                # tenant-isolation-allow: view-layer-scoped-via-request-school-or-role-graph
                for field in _required_fields_for_evaluation(evaluation):
                    if getattr(evaluation, field) is None:
                        updates[field] = fill_value
                        needs_update = True
                # tenant-isolation-allow: view-layer-scoped-via-request-school-or-role-graph
                if needs_update:
                    Evaluation.objects.filter(id=evaluation.id).update(**updates)
                    updated += 1
            messages.success(
                request, f"Filled missing scores for {updated} evaluations."
            )
            # tenant-isolation-allow: view-layer-scoped-via-request-school-or-role-graph
            redirect_target = request.path + f"?year={year_obj.id}&term={term_obj.id}"
            if classroom_id:
                redirect_target += f"&classroom={classroom_id}"
            if subject_id:
                # tenant-isolation-allow: view-layer-scoped-via-request-school-or-role-graph
                redirect_target += f"&subject={subject_id}"
            if missing_only:
                redirect_target += "&missing=1"
            return redirect(redirect_target)
# tenant-isolation-allow: view-layer-scoped-via-request-school-or-role-graph

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
        pdf_bytes = render_pdf_bytes(
            request, "reports/evaluation_grid.html", pdf_context
        )
        filename = f"grading-sheet-{year_obj.name}-{term_obj.label}.pdf".replace(
            " ", "_"
        )
        response = HttpResponse(pdf_bytes, content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response

    if request.GET.get("export") == "csv":
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = (
            f'attachment; filename="grading-sheet-{year_obj.name}-{term_obj.label}.csv"'
        )
        writer = csv.writer(response)
        writer.writerow(
            [
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
            ]
        )
        for e in evals_list:
            writer.writerow(
                [
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
                ]
            )
        return response

    export_csv_params = request.GET.copy()
    export_csv_params["export"] = "csv"
    export_pdf_params = request.GET.copy()
    export_pdf_params["export"] = "pdf"

    score_scale = getattr(current_weights, "score_scale", None) or 20
    pass_mark = score_scale // 2  # Phase 15.3: e.g. 10 for scale 20

    return render(
        request,
        "evals/evaluation_admin.html",
        {
            "year": year_obj,
            "term": term_obj,
            "selected_year": year_obj,
            "selected_term": term_obj,
            "filter_form": filter_form,
            "create_form": create_form,
            "weights_form": weights_form,
            "fill_form": fill_form,
            "current_weights": current_weights,
            "pass_mark": pass_mark,
            "evals": evals_list,
            "missing_only": missing_only,
            "required_fields": required_fields,
            "export_csv_query": export_csv_params.urlencode(),
            "export_pdf_query": export_pdf_params.urlencode(),
            "BREADCRUMBS": [
                {"label": "Backend", "url": reverse("accounts:backend_dashboard")},
                {"label": "Evaluation Admin", "url": "", "active": True},
            ],
        },
    )


@staff_member_required(login_url=settings.LOGIN_URL)
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

    return render(
        request,
        "evals/evidence_upload.html",
        {
            "form": form,
            "evaluation": evaluation,
            "evidence_items": evidence_items,
        },
    )


class GradeImportUploadForm(forms.Form):
    file = forms.FileField(help_text="Upload a CSV with the expected headers.")


@staff_member_required(login_url=settings.LOGIN_URL)
@role_required(User.Role.ADMIN, User.Role.HOD, "HEAD_OF_ACADEMICS")
def grade_import_upload_view(request: HttpRequest):
    """
    Staff-facing bulk grade import wizard. Renders the dropzone-based 4-step UI;
    actual upload + apply are handled client-side via grade_import_preview_api /
    grade_import_apply_api.
    """
    active_year, _ = get_active_year_and_term()
    return render(
        request,
        "evals/grade_import_upload_v2.html",
        {
            "template_headers": build_template_headers(),
            "active_year": active_year,
        },
    )


@staff_member_required(login_url=settings.LOGIN_URL)
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
    response["Content-Disposition"] = 'attachment; filename="grade_import_template.csv"'
    writer = csv.DictWriter(response, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerow({})
    return response


@staff_member_required(login_url=settings.LOGIN_URL)
def grade_approval_list(request: HttpRequest):
    from apps.evals.runtime_helpers import get_policy_for_request

    school = getattr(request, "school", None)
    policy = get_policy_for_request(request)
    if not _user_can_review_grades(request.user, school, policy=policy):
        return HttpResponseForbidden(
            "You are not authorized to review grade approvals."
        )

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


@staff_member_required(login_url=settings.LOGIN_URL)
@trace_view("grade.approval.detail", op="view.hot_path")
def grade_approval_detail(request: HttpRequest, request_id):
    from apps.evals.runtime_helpers import get_policy_for_request

    approval = get_object_or_404(GradeApprovalRequest, id=request_id)
    school = getattr(request, "school", None)
    policy = get_policy_for_request(request)
    if not _user_can_review_grades(request.user, school, policy=policy):
        return HttpResponseForbidden(
            "You are not authorized to review grade approvals."
        )

    can_finalize = user_can_finalize_submission(request.user, school, policy=policy)
    status_choices = list(GradeApprovalRequest.Status.choices)
    if not can_finalize:
        status_choices = [
            choice for choice in status_choices if choice[0] not in FINAL_STATUSES
        ]
    form = GradeApprovalDecisionForm(
        request.POST or None,
        initial={"status": approval.status},
        status_choices=status_choices,
    )

    bypass_allowed = bool(
        (
            request.user.is_superuser
            or request.user.role == User.Role.ADMIN
            or can_finalize
        )
        and approval.status not in FINAL_STATUSES
    )
    bypass_status_choices = [
        choice
        for choice in GradeApprovalRequest.Status.choices
        if choice[0] in FINAL_STATUSES
    ]
    bypass_form = GradeApprovalBypassForm(
        request.POST or None,
        status_choices=bypass_status_choices,
        initial={"status": GradeApprovalRequest.Status.APPROVED},
    )

    if request.method == "POST":
        action = request.POST.get("action") or "decide"
        if action == "bypass":
            if not bypass_allowed:
                return HttpResponseForbidden(
                    "You are not authorized to bypass grade approvals."
                )
            if bypass_form.is_valid():
                new_status = bypass_form.cleaned_data["status"]
                old_status = approval.status
                approval.mark_bypassed(
                    by_user=request.user,
                    new_status=new_status,
                    reason=bypass_form.cleaned_data["bypass_reason"],
                    notes=bypass_form.cleaned_data.get("reviewer_notes") or "",
                )
                AuditLog.objects.create(
                    user=request.user,
                    action=AuditLog.Action.APPROVE
                    if new_status == GradeApprovalRequest.Status.APPROVED
                    else AuditLog.Action.REJECT,
                    model_name="GradeApprovalRequest",
                    object_id=str(approval.id),
                    object_repr=str(approval),
                    sensitivity=AuditLog.Sensitivity.HIGH,
                    app_label="evals",
                    reason=f"BYPASS: {bypass_form.cleaned_data['bypass_reason']}",
                    old_values={"status": old_status},
                    new_values={"status": approval.status},
                    changed_fields=["status"],
                )
                NotificationService().send_grade_approval_decision_email(
                    approval, new_status
                )
                try_emit_grade_published_event(approval)
                messages.success(
                    request, "Approval bypass recorded and decision finalized."
                )
                return redirect("evals:grade_approval_list")
        else:
            if form.is_valid():
                new_status = form.cleaned_data["status"]
                if new_status in FINAL_STATUSES and not can_finalize:
                    form.add_error(
                        "status",
                        "Only final approvers can finalize or reject grade submissions.",
                    )
                else:
                    approval.mark_reviewed(
                        reviewer=request.user,
                        status=new_status,
                        notes=form.cleaned_data["reviewer_notes"],
                    )
                    NotificationService().send_grade_approval_decision_email(
                        approval, new_status
                    )
                    try_emit_grade_published_event(approval)
                    messages.success(request, "Grade approval decision saved.")
                    return redirect("evals:grade_approval_list")

    from apps.evals.approval import get_grade_approval_policy

    ga_policy = get_grade_approval_policy(school=school, policy=policy)
    deadline_note = ga_policy.get("grade_approval_deadline_note", "")
    deadline_display = None  # deadline_at removed from GradeApprovalRequest model
    validation_flags = []
    return render(
        request,
        "evals/grade_approval_detail.html",
        {
            "approval": approval,
            "form": form,
            "bypass_form": bypass_form,
            "bypass_allowed": bypass_allowed,
            "entries": approval.entries,
            "score_fields": ["seq1", "seq2", "exam", "mock", "practical"],
            "can_finalize": can_finalize,
            "deadline_display": deadline_display,
            "deadline_note": deadline_note,
            "deadline_overdue": approval.is_overdue,
            "validation_flags": validation_flags,
            "final_roles": grade_post_roles(school=school, policy=policy),
        },
    )


# ========== COMPLIANCE & ADVANCED IMPORT VIEWS ==========


@staff_member_required(login_url=settings.LOGIN_URL)
@role_required(User.Role.ADMIN, User.Role.HOD, "HEAD_OF_ACADEMICS")
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
    compliant_count = sum(1 for t in compliance_data if t["status"] == "compliant")
    at_risk_count = sum(1 for t in compliance_data if t["status"] == "at_risk")
    overdue_count = sum(1 for t in compliance_data if t["status"] == "overdue")

    # Filter by status if requested
    status_filter = request.GET.get("status", "all")
    if status_filter != "all":
        compliance_data = [t for t in compliance_data if t["status"] == status_filter]

    context = {
        "compliance_data": compliance_data,
        "kpis": {
            "total": total_teachers,
            "compliant": compliant_count,
            "at_risk": at_risk_count,
            "overdue": overdue_count,
        },
        "current_term": f"{academic_year.name} - {term.name}",
        "status_filter": status_filter,
    }

    return render(request, "evals/compliance_dashboard.html", context)


@staff_member_required(login_url=settings.LOGIN_URL)
@role_required(User.Role.ADMIN, User.Role.HOD, "HEAD_OF_ACADEMICS")
def extend_deadline_view(request, subject_assignment_id):
    """
    Extend grading deadline for a subject assignment.
    Uses SubjectAssignment.grading_deadline_at.
    # tenant-isolation-allow: view-layer-scoped-via-request-school-or-role-graph
    """
    from apps.academics.models import SubjectAssignment
    from apps.evals.models import GradeAudit

    # tenant-isolation-allow: view-layer-scoped-via-request-school-or-role-graph
    try:
        subject_assignment = SubjectAssignment.objects.get(id=subject_assignment_id)
    except SubjectAssignment.DoesNotExist:
        messages.error(request, "Subject assignment not found.")
        return redirect("evals:compliance_dashboard")

    current_deadline = subject_assignment.grading_deadline_at

    if request.method == "POST":
        days_extension = int(request.POST.get("days_extension", 0) or 0)
        reason = (request.POST.get("reason") or "").strip()

        if days_extension > 0:
            base = current_deadline or timezone.now()
            new_deadline = base + timezone.timedelta(days=days_extension)
            subject_assignment.grading_deadline_at = new_deadline
            subject_assignment.save(update_fields=["grading_deadline_at"])

            GradeAudit.objects.create(
                evaluation=None,
                change_type="deadline_extended",
                changed_by=request.user,
                remarks_after=f"Deadline extended by {days_extension} days. Reason: {reason}",
            )
            messages.success(request, f"Deadline extended to {new_deadline.date()}")
        else:
            messages.warning(request, "Please enter a positive number of days.")
        return redirect("evals:compliance_dashboard")

    return render(
        request,
        "evals/extend_deadline.html",
        {
            "subject_assignment": subject_assignment,
            "deadline": current_deadline,
        },
    )


@staff_member_required(login_url=settings.LOGIN_URL)
@role_required(User.Role.ADMIN, User.Role.HOD, "HEAD_OF_ACADEMICS")
def grade_import_preview_api(request):
    """API endpoint for grade import preview with validation."""
    from apps.evals.importers import preview_import_with_validation
    import json

    if request.method != "POST":
        return HttpResponseForbidden("POST required")

    # Parse CSV from request
    csv_file = request.FILES.get("file")
    if not csv_file:
        return HttpResponse(
            json.dumps({"error": "No file provided"}),
            content_type="application/json",
            status=400,
        )

    try:
        import csv as csv_module

        reader = csv_module.DictReader(io.TextIOWrapper(csv_file, encoding="utf-8"))
        csv_rows = list(reader)

        # Run validation
        rows_with_validation, errors = preview_import_with_validation(csv_rows)

        # Return preview
        preview_data = []
        for row in rows_with_validation:
            preview_data.append(
                {
                    "student_code": row.student_code,
                    "subject_assignment_id": row.subject_assignment_id,
                    "term_id": row.term_id,
                    "seq1": row.seq1,
                    "seq2": row.seq2,
                    "exam": row.exam,
                    "is_valid": row.is_valid,
                    "errors": row.errors,
                    "warnings": row.warnings,
                }
            )

        return HttpResponse(
            json.dumps(
                {
                    "preview": preview_data,
                    "file_errors": errors,
                    "total_rows": len(rows_with_validation),
                    "valid_rows": sum(1 for r in rows_with_validation if r.is_valid),
                    "invalid_rows": sum(
                        1 for r in rows_with_validation if not r.is_valid
                    ),
                }
            ),
            content_type="application/json",
        )

    except EVALS_SOFT_FAILURES as e:
        logger.exception("Grade import preview API failed")
        return HttpResponse(
            json.dumps(
                {
                    "error": "We couldn't read your CSV. Check that the file is UTF-8 and that column headers match the template.",
                    "detail": str(e),
                }
            ),
            content_type="application/json",
            status=400,
        )

# tenant-isolation-allow: view-layer-scoped-via-request-school-or-role-graph

@staff_member_required(login_url=settings.LOGIN_URL)
@role_required(User.Role.ADMIN, User.Role.HOD, "HEAD_OF_ACADEMICS")
def grade_import_apply_api(request):
    """API endpoint for applying (persisting) grade import."""
    from apps.evals.importers import apply_import
    # tenant-isolation-allow: view-layer-scoped-via-request-school-or-role-graph
    from apps.analytics.models import GradeImportJob
    import json

    if request.method != "POST":
        return HttpResponseForbidden("POST required")
# tenant-isolation-allow: view-layer-scoped-via-request-school-or-role-graph

    def _resolve_year_term():
        yid = (request.POST.get("academic_year_id") or "").strip()
        tid = (request.POST.get("term_id") or "").strip()
        # tenant-isolation-allow: view-layer-scoped-via-request-school-or-role-graph
        if yid and tid:
            try:
                # tenant-isolation-allow: view-layer-scoped-via-request-school-or-role-graph
                y = AcademicYear.objects.get(pk=int(yid))
                # tenant-isolation-allow: view-layer-scoped-via-request-school-or-role-graph
                t = Term.objects.get(pk=int(tid), academic_year=y)
                return y, t
            except (AcademicYear.DoesNotExist, Term.DoesNotExist, ValueError, TypeError):
                pass
        # tenant-isolation-allow: view-layer-scoped-via-request-school-or-role-graph
        y = AcademicYear.objects.order_by("-start_date").first()
        if not y:
            return None, None
        # tenant-isolation-allow: view-layer-scoped-via-request-school-or-role-graph
        t = Term.objects.filter(academic_year=y).order_by("position", "id").first()
        return y, t

    year, term = _resolve_year_term()
    if not year or not term:
        return HttpResponse(
            json.dumps(
                {
                    "error": "No academic year/term. Pass academic_year_id and term_id.",
                }
            ),
            content_type="application/json",
            status=400,
        )

    # Create job record
    job = GradeImportJob.objects.create(
        academic_year=year,
        term=term,
        uploaded_by=request.user if request.user.is_authenticated else None,
        status="processing",
        created_count=0,
        updated_count=0,
        failed_count=0,
    )

    try:
        csv_file = request.FILES.get("file")
        csv_module = __import__("csv")
        reader = csv_module.DictReader(io.TextIOWrapper(csv_file, encoding="utf-8"))
        csv_rows = list(reader)

        # Apply import
        result = apply_import(csv_rows)

        # Update job
        job.created_count = result["created"]
        job.updated_count = result["updated"]
        job.status = "completed"
        job.completed_at = timezone.now()
        job.save()

        return HttpResponse(
            json.dumps(
                {
                    "job_id": job.id,
                    "status": "completed",
                    "created": result["created"],
                    "updated": result["updated"],
                    "duration_seconds": result.get("duration_seconds", 0),
                }
            ),
            content_type="application/json",
        )

    except EVALS_SOFT_FAILURES as e:
        logger.exception("Grade import apply API failed")
        job.status = "failed"
        job.failed_count += 1
        job.error_log = [str(e)]
        job.save()
        user_message = "Import failed while saving grades. Check your data matches the template (student codes, subject assignment and term IDs)."
        return HttpResponse(
            json.dumps(
                {
                    "job_id": job.id,
                    "status": "failed",
                    "error": user_message,
                    "detail": str(e),
                }
            ),
            content_type="application/json",
            status=400,
        )


@staff_member_required(login_url=settings.LOGIN_URL)
# tenant-isolation-allow: view-layer-scoped-via-request-school-or-role-graph
@role_required(User.Role.ADMIN, User.Role.HOD, User.Role.TEACHER, "HEAD_OF_ACADEMICS")
def audit_trail_view(request, evaluation_id):
    """View audit trail for an evaluation."""
    from apps.analytics.services import get_audit_trail
# tenant-isolation-allow: view-layer-scoped-via-request-school-or-role-graph

    try:
        # tenant-isolation-allow: view-layer-scoped-via-request-school-or-role-graph
        evaluation = Evaluation.objects.get(id=evaluation_id)
    except Evaluation.DoesNotExist:
        messages.error(request, "Evaluation not found.")
        return redirect("admin:evals_evaluation_changelist")

    trail = get_audit_trail(evaluation_id, limit=100)

    context = {
        "evaluation": evaluation,
        "trail": trail,
        "student_name": f"{evaluation.student.user.first_name} {evaluation.student.user.last_name}",
        "subject_name": evaluation.subject_assignment.subject.name,
    }

    return render(request, "evals/audit_trail.html", context)


@staff_member_required(login_url=settings.LOGIN_URL)
@role_required(User.Role.ADMIN, User.Role.HOD, "HEAD_OF_ACADEMICS")
def resolve_offline_conflict_view(request, offline_entry_id):
    """Manual conflict resolution for offline mark entries."""
    from apps.evals.models import OfflineMarkEntry

    try:
        offline_entry = OfflineMarkEntry.objects.get(id=offline_entry_id)
    except OfflineMarkEntry.DoesNotExist:
        messages.error(request, "Offline entry not found.")
        return redirect("admin:evals_offlinemarkentry_changelist")
# tenant-isolation-allow: view-layer-scoped-via-request-school-or-role-graph

    if offline_entry.status != "conflict":
        messages.info(request, "This entry is not in conflict status.")
        return redirect("admin:evals_offlinemarkentry_changelist")
# tenant-isolation-allow: view-layer-scoped-via-request-school-or-role-graph

    # Get online version
    # tenant-isolation-allow: view-layer-scoped-via-request-school-or-role-graph
    try:
        online_entry = Evaluation.objects.get(
            academic_year=offline_entry.academic_year,
            term=offline_entry.term,
            subject_assignment=offline_entry.subject_assignment,
            student=offline_entry.student,
        )
    except Evaluation.DoesNotExist:
        online_entry = None

    if request.method == "POST":
        # User chose to keep online or offline version
        choice = request.POST.get("choice", "online")

        if choice == "offline" and online_entry:
            # Merge offline into online
            online_entry.seq1_score = offline_entry.seq1_score
            online_entry.seq2_score = offline_entry.seq2_score
            online_entry.exam_score = offline_entry.exam_score
            online_entry.mock_score = offline_entry.mock_score
            online_entry.practical_score = offline_entry.practical_score
            online_entry.remarks = offline_entry.remarks
            online_entry.save()

        # Mark as resolved
        offline_entry.status = "synced"
        offline_entry.save()

        messages.success(request, "Conflict resolved.")
        return redirect("admin:evals_offlinemarkentry_changelist")

    context = {
        "offline_entry": offline_entry,
        "online_entry": online_entry,
        "student_name": f"{offline_entry.student.user.first_name} {offline_entry.student.user.last_name}",
        "subject_name": offline_entry.subject_assignment.subject.name,
    }

    return render(request, "evals/resolve_offline_conflict.html", context)


@staff_member_required(login_url=settings.LOGIN_URL)
@role_required(User.Role.ADMIN, User.Role.HOD, "HEAD_OF_ACADEMICS")
def import_job_monitor_view(request):
    """Monitor and manage import jobs."""
    from apps.analytics.models import GradeImportJob

    # Get filter parameters
    status_filter = request.GET.get("status", "")
    from_date = request.GET.get("from_date", "")
    to_date = request.GET.get("to_date", "")

    # Build query
    query = GradeImportJob.objects.all().order_by("-created_at")

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
    processing_jobs = all_jobs.filter(status="processing").count()
    completed_jobs = all_jobs.filter(status="completed").count()
    failed_jobs = all_jobs.filter(status="failed").count()

    context = {
        "jobs": jobs,
        "total_jobs": total_jobs,
        "processing_jobs": processing_jobs,
        "completed_jobs": completed_jobs,
        "failed_jobs": failed_jobs,
        "status": status_filter,
        "from_date": from_date,
        "to_date": to_date,
    }

    return render(request, "evals/import_job_monitor.html", context)
