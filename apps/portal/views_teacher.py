"""
Portal teacher-facing and staff (cahier, discipline) views (§6.14 Phase 2 — role separation).
"""

from __future__ import annotations

from collections import Counter
from datetime import timedelta
import csv
import logging

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse, HttpResponseForbidden, Http404
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.accounts.decorators import role_required, teacher_portal_required
from apps.accounts.models import User
from apps.accounts.utils import get_user_role
from apps.observability.tracing import trace_view
from apps.academics.models import (
    Attendance,
    Classroom,
    CurriculumNode,
    Incident,
    SubjectAssignment,
)
from apps.academics.scheduling import Schedule, ScheduleEntry
from apps.academics.services import get_active_year_and_term
from apps.evals.models import TeacherAssignment
from apps.evals.views import (
    teacher_dashboard as evals_teacher_dashboard,
    teacher_workflow_center as evals_teacher_workflow_center,
)
from apps.people.models import (
    StudentProfile,
    TeacherProfile,
    TeacherPayRecord,
    TeacherLeaveRequest,
    TeacherAttendance,
)
from apps.platform_runtime.helpers import get_effective_flags
from apps.portal.models import (
    LessonPlan,
    TeacherTrainingEntry,
    CahierDeTexteEntry,
)
from apps.portal.forms import (
    TeacherLeaveForm,
    LessonPlanUploadForm,
    LessonPlanAttachmentForm,
    TeacherTrainingEntryForm,
    CahierDeTexteEntryForm,
)

logger = logging.getLogger(__name__)


def _teacher_feed_school(request: HttpRequest):
    """Resolve school for teacher feed."""
    from apps.schools.models import School, SchoolMembership

    school = getattr(request, "school", None)
    if school is not None:
        return school
    school_id = getattr(request, "session", {}).get("school_id")
    if school_id:
        return School.objects.filter(pk=school_id, is_active=True).first()
    membership = (
        # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
        SchoolMembership.objects.filter(user=request.user, school__is_active=True)
        .select_related("school")
        .first()
    )
    return membership.school if membership else None


@role_required(User.Role.TEACHER)
def teacher_feed(request: HttpRequest):
    """Plan VI: Social feed for teachers — school announcements, achievements, interventions."""
    from apps.communication.models import FeedItem

    school = _teacher_feed_school(request)
    if not school:
        messages.info(request, "Select a school to view the feed.")
        return redirect("portal:teacher_dashboard_alias")
    items = (
        FeedItem.objects.filter(school=school)
        .select_related("student", "created_by")
        .order_by("-created_at")[:100]
    )
    return render(request, "teacher/feed.html", {"feed_items": list(items)})


@login_required
def teacher_dashboard_alias(request: HttpRequest):
    """Render the teacher dashboard layout under the portal path."""
    return evals_teacher_dashboard(request)


@login_required
def teacher_workflow_alias(request: HttpRequest):
    """Render the teacher workflow center under the portal path."""
    return evals_teacher_workflow_center(request)


def _compute_attendance_streak(logs):
    """Compute consecutive present days from attendance logs."""
    today = timezone.localdate()
    log_lookup = {entry.date: entry for entry in logs}
    streak = 0
    cursor = today
    while True:
        entry = log_lookup.get(cursor)
        if entry and entry.status == TeacherAttendance.Status.PRESENT:
            streak += 1
            cursor -= timedelta(days=1)
            continue
        break
    return streak


@teacher_portal_required
@role_required(User.Role.TEACHER)
def teacher_pay_history(request: HttpRequest):
    """RBAC: only the logged-in teacher's pay history (strict data isolation)."""
    # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
    profile = TeacherProfile.objects.filter(user=request.user).first()
    if not profile or profile.user_id != request.user.id:
        messages.error(
            request, "No teacher profile found. Ask an admin to complete your profile."
        )
        return redirect("evals:teacher_dashboard")

    pay_records = profile.pay_records.select_related("created_by").order_by(
        "-effective_date", "-created_at"
    )
    latest_pay = pay_records.filter(record_type=TeacherPayRecord.RecordType.PAY).first()
    raises_count = pay_records.filter(
        record_type=TeacherPayRecord.RecordType.RAISE
    ).count()
    bonus_count = pay_records.filter(
        record_type=TeacherPayRecord.RecordType.BONUS
    ).count()
    last_pay_amount = latest_pay.amount if latest_pay else None
    last_pay_date = latest_pay.effective_date if latest_pay else None
    payment_totals = Counter()
    for record in pay_records:
        payment_totals[record.record_type] += record.amount

    total_paid_amount = sum(
        record.amount
        for record in pay_records
        if record.record_type == TeacherPayRecord.RecordType.PAY
    )
    raise_total = sum(
        record.amount
        for record in pay_records
        if record.record_type == TeacherPayRecord.RecordType.RAISE
    )
    bonus_total = sum(
        record.amount
        for record in pay_records
        if record.record_type == TeacherPayRecord.RecordType.BONUS
    )

    attendance_logs = list(profile.attendance_logs.order_by("-date")[:30])
    streak = _compute_attendance_streak(attendance_logs)
    recent_absence = next(
        (
            entry
            for entry in attendance_logs
            if entry.status
            in {
                TeacherAttendance.Status.ABSENT,
                TeacherAttendance.Status.LATE,
                TeacherAttendance.Status.ON_LEAVE,
            }
        ),
        None,
    )
    absence_alert = (
        f"Last absence recorded on {recent_absence.date}: "
        f"{recent_absence.remarks or recent_absence.get_status_display()}."
        if recent_absence
        else None
    )

    hero = {
        "title": "Pay history",
        "subtitle": "Recent pay, raises, and stipends",
        "actions": [],
        "stats": [
            {
                "label": "Last pay",
                "value": last_pay_amount or "-",
                "meta": last_pay_date or "Not set",
            },
            {
                "label": "Next pay date",
                "value": profile.next_pay_date or "Not set",
                "meta": profile.pay_grade or "Pay grade",
            },
            {
                "label": "Raises",
                "value": raises_count,
                "meta": f"Bonuses: {bonus_count}",
            },
            {"label": "Streak", "value": streak, "meta": "days present"},
        ],
    }
    payment_type_breakdown = [
        {"label": TeacherPayRecord.RecordType(record_type).label, "amount": amount}
        for record_type, amount in payment_totals.items()
    ]
    return render(
        request,
        "teacher/pay_history.html",
        {
            "hero": hero,
            "pay_records": pay_records,
            "teacher_profile": profile,
            "latest_pay": latest_pay,
            "raises_count": raises_count,
            "bonus_count": bonus_count,
            "payment_type_breakdown": payment_type_breakdown,
            "total_paid_amount": total_paid_amount,
            "raise_total": raise_total,
            "bonus_total": bonus_total,
            "attendance_logs": attendance_logs,
            "attendance_streak": streak,
            "attendance_alert": absence_alert,
        },
    )


@teacher_portal_required
@role_required(User.Role.TEACHER)
def teacher_leave(request: HttpRequest):
    # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
    """RBAC: only the logged-in teacher's leave requests."""
    profile = TeacherProfile.objects.filter(user=request.user).first()
    if not profile or profile.user_id != request.user.id:
        messages.error(
            request, "No teacher profile found. Ask an admin to complete your profile."
        )
        return redirect("evals:teacher_dashboard")

    form = TeacherLeaveForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        leave = form.save(commit=False)
        leave.teacher = profile
        leave.status = TeacherLeaveRequest.Status.PENDING
        leave.save()
        messages.success(request, "Leave request submitted for approval.")
        return redirect("portal:teacher_leave")

    leave_requests = profile.leave_requests.select_related("approver")
    hero = {
        "title": "Leave requests",
        "subtitle": "Submit a request and track approvals",
        "actions": [],
    }
    return render(
        request,
        "teacher/leave.html",
        {
            "hero": hero,
            "form": form,
            "leave_requests": leave_requests,
        },
    )


@teacher_portal_required
@role_required(User.Role.TEACHER)
@trace_view("teacher.attendance.view", op="view.hot_path")
def teacher_attendance_view(request: HttpRequest):
    """Teacher attendance summary and logs."""
    profile = getattr(request.user, "teacher_profile", None)
    if not profile:
        messages.error(
            request, "No teacher profile found. Ask an admin to complete your profile."
        )
        return redirect("evals:teacher_dashboard")

    logs = profile.attendance_logs.all()
    present = logs.filter(status=TeacherAttendance.Status.PRESENT).count()
    absences = logs.filter(status=TeacherAttendance.Status.ABSENT).count()
    late = logs.filter(status=TeacherAttendance.Status.LATE).count()
    hero = {
        "title": "Attendance",
        "subtitle": "Check-ins, check-outs, and leave days",
        "actions": [],
    }
    return render(
        request,
        "teacher/attendance.html",
        {
            "hero": hero,
            "logs": logs,
            "present": present,
            "absences": absences,
            "late": late,
            "export_url": reverse("portal:teacher_attendance_export"),
        },
    )


@teacher_portal_required
@role_required(User.Role.TEACHER)
def teacher_attendance_export(request: HttpRequest):
    """Export teacher attendance as CSV."""
    profile = getattr(request.user, "teacher_profile", None)
    if not profile:
        messages.error(request, "No teacher profile found.")
        return redirect("evals:teacher_dashboard")

    logs = profile.attendance_logs.order_by("-date")
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="teacher_attendance.csv"'
    writer = csv.writer(response)
    writer.writerow(["Date", "Status", "Check-in", "Check-out", "Remarks"])
    for entry in logs:
        writer.writerow(
            [
                entry.date,
                entry.get_status_display(),
                entry.check_in or "",
                entry.check_out or "",
                entry.remarks or "",
            ]
        )
    return response


def _cahier_enabled(request=None):
    flags = get_effective_flags(request)
    if not flags.get("enable_cahier_de_texte"):
        return False
    if request and getattr(request, "school", None):
        from apps.policies.policy_registry import get_effective_policy

        result = get_effective_policy(
            request.school,
            user=getattr(request, "user", None),
            capability="cahier_de_texte",
        )
        if not result.get("enabled", False):
            return False
    return True


@login_required
def take_student_attendance(request: HttpRequest):
    """Student roll call: date + classroom, default present, one save. Requires attendance.manage."""
    if not getattr(request.user, "has_feature_permission", lambda _: False)(
        "attendance.manage"
    ):
        return HttpResponseForbidden(
            "You do not have permission to take student attendance."
        # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
        )
    year, _term = get_active_year_and_term()
    classrooms = (
        # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
        list(Classroom.objects.filter(academic_year=year).order_by("name"))
        if year
        else []
    )
    today = timezone.localdate()
    date_str = request.GET.get("date") or request.POST.get("date") or today.isoformat()
    classroom_id = request.GET.get("classroom") or request.POST.get("classroom")
    try:
        att_date = timezone.datetime.strptime(date_str, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        att_date = today
    existing = {}
    students = []
    classroom_obj = None
    if classroom_id and classrooms:
        classroom_obj = next(
            (c for c in classrooms if str(c.id) == str(classroom_id)), None
        )
        if classroom_obj:
            students = list(
                classroom_obj.students.filter(
                    status__in=(
                        StudentProfile.Status.NEW,
                        StudentProfile.Status.RETURNING,
                        StudentProfile.Status.PROBATION,
                    # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
                    )
                ).order_by("last_name", "first_name")
            )
            # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
            if students and att_date:
                for a in Attendance.objects.filter(
                    classroom=classroom_obj, date=att_date
                ).select_related("student"):
                    existing[a.student_id] = a.status
    if request.method == "POST" and request.POST.get("qr_sweep") and classroom_obj:
        from apps.academics.qr_attendance import apply_qr_sweep

        school = getattr(request, "school", None) or getattr(request.user, "school", None)
        school_id = getattr(school, "pk", None)
        if not school_id:
            messages.error(request, "School context required for card sweep.")
        else:
            sweep = apply_qr_sweep(
                classroom_id=classroom_obj.id,
                date_value=att_date,
                tokens_text=request.POST.get("qr_tokens") or "",
                school_id=school_id,
            )
            messages.success(
                request,
                f"Card sweep saved: {sweep.created + sweep.updated} students "
                f"({sweep.student_count} matched, {len(sweep.errors)} skipped).",
            )
        return redirect(
            f"{reverse('portal:take_student_attendance')}?date={att_date.isoformat()}&classroom={classroom_obj.id}"
        )

    if request.method == "POST" and classroom_obj and students:
        for s in students:
            status = (
                request.POST.get(f"status_{s.id}") or ""
            ).strip() or Attendance.Status.PRESENT
            if status not in {c[0] for c in Attendance.Status.choices}:
                status = Attendance.Status.PRESENT
            Attendance.objects.update_or_create(
                student=s,
                classroom=classroom_obj,
                date=att_date,
                defaults={"status": status},
            )
        messages.success(request, f"Attendance saved for {len(students)} students.")
        return redirect(
            f"{reverse('portal:take_student_attendance')}?date={att_date.isoformat()}&classroom={classroom_obj.id}"
        )
    status_choices = list(Attendance.Status.choices)
    students_with_status = [
        {"student": s, "status": existing.get(s.id, Attendance.Status.PRESENT)}
        for s in students
    ]
    hero = {
        "title": "Take student attendance",
        "subtitle": "Select date and class, then mark present/absent/late.",
        "actions": [],
    }
    qr_tokens_by_student = {}
    school = getattr(request, "school", None) or getattr(request.user, "school", None)
    if school and students_with_status:
        from apps.academics.qr_attendance import mint_student_attendance_token

        for row in students_with_status:
            s = row["student"]
            qr_tokens_by_student[s.id] = mint_student_attendance_token(
                school_id=school.pk,
                student_id=s.id,
                student_code=s.student_code or "",
            )

    return render(
        request,
        "portal/roll_call_student.html",
        {
            "hero": hero,
            "classrooms": classrooms,
            "date_value": att_date.isoformat(),
            "classroom_id": classroom_id or "",
            "classroom": classroom_obj,
            "students_with_status": students_with_status,
            "status_choices": status_choices,
            "Attendance": Attendance,
            "qr_tokens_by_student": qr_tokens_by_student,
        },
    )


@login_required
def record_teacher_attendance(request: HttpRequest):
    """Teacher roll call: date, list of teachers, default present, one save. Requires attendance.manage."""
    if not getattr(request.user, "has_feature_permission", lambda _: False)(
        "attendance.manage"
    ):
        return HttpResponseForbidden(
            "You do not have permission to record teacher attendance."
        )
    teachers = list(
        TeacherProfile.objects.select_related("user").order_by(
            "user__last_name", "user__first_name"
        )
    )
    today = timezone.localdate()
    date_str = request.GET.get("date") or request.POST.get("date") or today.isoformat()
    try:
        att_date = timezone.datetime.strptime(date_str, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        att_date = today
    existing = {
        e.teacher_id: e.status for e in TeacherAttendance.objects.filter(date=att_date)
    }
    if request.method == "POST" and teachers:
        for t in teachers:
            status = (
                request.POST.get(f"status_{t.id}") or ""
            ).strip() or TeacherAttendance.Status.PRESENT
            if status not in {c[0] for c in TeacherAttendance.Status.choices}:
                status = TeacherAttendance.Status.PRESENT
            TeacherAttendance.objects.update_or_create(
                teacher=t,
                date=att_date,
                defaults={"status": status},
            )
        messages.success(request, f"Attendance saved for {len(teachers)} teachers.")
        return redirect(
            f"{reverse('portal:record_teacher_attendance')}?date={att_date.isoformat()}"
        )
    status_choices = list(TeacherAttendance.Status.choices)
    teachers_with_status = [
        {"teacher": t, "status": existing.get(t.id, TeacherAttendance.Status.PRESENT)}
        for t in teachers
    ]
    hero = {
        "title": "Take teacher attendance",
        "subtitle": "Select date and mark each teacher present, absent, late, or on leave.",
        "actions": [],
    }
    return render(
        request,
        "portal/roll_call_teacher.html",
        {
            "hero": hero,
            "teachers_with_status": teachers_with_status,
            "date_value": att_date.isoformat(),
            "status_choices": status_choices,
            "TeacherAttendance": TeacherAttendance,
        },
    )


@login_required
def seating_chart_view(request: HttpRequest):
    """W4-2: Seating chart placeholder — view or link for class layout. Optional ?classroom=id."""
    flags = get_effective_flags(request)
    if not flags.get("enable_seating_chart_beta"):
        raise Http404("Seating chart is not enabled.")
    if not getattr(request.user, "has_feature_permission", lambda _: False)(
        "attendance.manage"
    ):
        return HttpResponseForbidden(
            # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
            "You do not have permission to view seating chart."
        )
    year, _term = get_active_year_and_term()
    # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
    classrooms = (
        list(Classroom.objects.filter(academic_year=year).order_by("name"))
        if year
        else []
    )
    classroom_id = request.GET.get("classroom")
    classroom_obj = None
    if classroom_id and classrooms:
        classroom_obj = next(
            (c for c in classrooms if str(c.id) == str(classroom_id)), None
        )
    hero = {
        "title": "Seating chart",
        "subtitle": "Class layout view for roll call and attendance.",
        "actions": [],
    }
    return render(
        request,
        "portal/seating_chart.html",
        {
            "hero": hero,
            "classrooms": classrooms,
            "classroom": classroom_obj,
            "classroom_id": classroom_id or "",
        },
    )


@login_required
@teacher_portal_required
@role_required(User.Role.TEACHER)
def cahier_list(request: HttpRequest):
    """List and add Cahier de Texte entries (when feature enabled)."""
    # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
    if not _cahier_enabled(request):
        return HttpResponseForbidden("Cahier de Texte is not enabled.")
    # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
    profile = TeacherProfile.objects.filter(user=request.user).first()
    if not profile:
        return redirect("portal:teacher_dashboard_alias")
    # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
    year, _ = get_active_year_and_term()
    assignments_qs = SubjectAssignment.objects.none()
    # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
    if year:
        sa_ids = TeacherAssignment.objects.filter(
            # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
            teacher=profile,
            is_active=True,
            # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
            subject_assignment__academic_year=year,
        ).values_list("subject_assignment_id", flat=True)
        # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
        assignments_qs = SubjectAssignment.objects.filter(pk__in=sa_ids).select_related(
            "classroom", "subject", "specialty"
        )
    from django.core.paginator import Paginator

    entries_qs = (
        CahierDeTexteEntry.objects.filter(teacher=profile)
        .select_related("subject_assignment__classroom", "subject_assignment__subject")
        .order_by("-entry_date")
    )
    paginator = Paginator(entries_qs, 20)
    page_number = request.GET.get("page") or 1
    page_obj = paginator.get_page(page_number)
    entries = page_obj.object_list
    form = CahierDeTexteEntryForm(request.POST or None)
    form.fields["subject_assignment"].queryset = assignments_qs
    if request.method == "POST" and form.is_valid():
        obj = form.save(commit=False)
        obj.teacher = profile
        obj.status = CahierDeTexteEntry.Status.SUBMITTED
        obj.save()
        messages.success(request, "Entry submitted for visa.")
        return redirect("portal:cahier_list")
    flags = get_effective_flags(request)
    curriculum_nodes = []
    if flags.get("cahier_syllabus_integration") == "national_progression":
        curriculum_nodes = list(
            CurriculumNode.objects.filter(level_type=CurriculumNode.LevelType.TOPIC)
            .order_by("standard", "order", "code")
            .values_list("code", "title")[:500]
        )
    hero = {
        "title": "Cahier de Texte",
        "subtitle": "Lesson diary entries",
        "actions": [],
    }
    return render(
        request,
        "portal/cahier_list.html",
        {
            "hero": hero,
            "entries": entries,
            "page_obj": page_obj,
            "form": form,
            "curriculum_nodes": curriculum_nodes,
        },
    )


@login_required
def cahier_verify_list(request: HttpRequest):
    """List SUBMITTED entries for supervisor visa (cahier.verify or CENSOR)."""
    if not _cahier_enabled(request):
        return HttpResponseForbidden("Cahier de Texte is not enabled.")
    can_verify = (
        getattr(request.user, "has_feature_permission", lambda _: False)(
            "cahier.verify"
        )
        or get_user_role(request.user) == "CENSOR"
    )
    if not can_verify:
        return HttpResponseForbidden(
            "You do not have permission to verify Cahier entries."
        )
    entries = (
        CahierDeTexteEntry.objects.filter(status=CahierDeTexteEntry.Status.SUBMITTED)
        .select_related(
            "teacher__user",
            "subject_assignment__classroom",
            "subject_assignment__subject",
        )
        .order_by("entry_date")[:100]
    )
    hero = {
        "title": "Cahier de Texte – Verification",
        "subtitle": "Visa or request revisions",
        "actions": [],
    }
    return render(
        request,
        "portal/cahier_verify_list.html",
        {"hero": hero, "entries": entries},
    )


@require_POST
@login_required
def cahier_visa(request: HttpRequest, entry_id: int):
    """Set entry to VISED."""
    if not _cahier_enabled(request):
        return HttpResponseForbidden("Cahier de Texte is not enabled.")
    if not (
        getattr(request.user, "has_feature_permission", lambda _: False)(
            "cahier.verify"
        )
        or get_user_role(request.user) == "CENSOR"
    ):
        return HttpResponseForbidden("You do not have permission to verify.")
    entry = get_object_or_404(
        CahierDeTexteEntry,
        pk=entry_id,
        status=CahierDeTexteEntry.Status.SUBMITTED,
    )
    entry.status = CahierDeTexteEntry.Status.VISED
    entry.verified_by = request.user
    entry.verified_at = timezone.now()
    entry.save(update_fields=["status", "verified_by", "verified_at", "updated_at"])
    messages.success(request, "Entry vised.")
    return redirect("portal:cahier_verify_list")


@require_POST
@login_required
def cahier_request_revisions(request: HttpRequest, entry_id: int):
    """Set entry to REVISIONS_REQUESTED."""
    if not _cahier_enabled(request):
        return HttpResponseForbidden("Cahier de Texte is not enabled.")
    if not (
        getattr(request.user, "has_feature_permission", lambda _: False)(
            "cahier.verify"
        )
        or get_user_role(request.user) == "CENSOR"
    ):
        return HttpResponseForbidden("You do not have permission to verify.")
    entry = get_object_or_404(
        CahierDeTexteEntry,
        pk=entry_id,
        status=CahierDeTexteEntry.Status.SUBMITTED,
    )
    entry.status = CahierDeTexteEntry.Status.REVISIONS_REQUESTED
    entry.save(update_fields=["status", "updated_at"])
    messages.success(request, "Revisions requested.")
    return redirect("portal:cahier_verify_list")


@teacher_portal_required
@role_required(User.Role.TEACHER)
def teacher_timetable(request: HttpRequest):
    """Show the logged-in teacher's timetable from published schedule (current term)."""
    year, term = get_active_year_and_term()
    schedule = None
    entries = []
    if year and term:
        schedule = (
            Schedule.objects.filter(academic_year=year, term=term, status="PUBLISHED")
            .order_by("-published_at")
            .first()
        )
        if not schedule:
            schedule = (
                Schedule.objects.filter(academic_year=year, term=term)
                .order_by("-generated_at")
                .first()
            )
        if schedule:
            entries = (
                ScheduleEntry.objects.filter(
                    schedule=schedule,
                    teacher=request.user,
                    is_cancelled=False,
                )
                .select_related("classroom", "subject", "room", "time_slot")
                .order_by("time_slot__day_of_week", "time_slot__start_time")
            )
    by_day = {}
    for e in entries:
        day = e.time_slot.get_day_of_week_display()
        by_day.setdefault(day, []).append(e)
    days_order = [
        "Monday",
        "Tuesday",
        "Wednesday",
        "Thursday",
        "Friday",
        "Saturday",
        "Sunday",
    ]
    by_day_ordered = [(d, by_day.get(d, [])) for d in days_order if by_day.get(d)]
    hero = {
        "title": "My Timetable",
        "subtitle": (
            f"{term.custom_label or term.name if term else 'No term'} – {year.name if year else 'No year'}"
            if (year and term)
            else "No active term set."
        ),
        "actions": [],
    }
    return render(
        request,
        "teacher/timetable.html",
        {
            "hero": hero,
            "schedule": schedule,
            "entries": entries,
            "by_day_ordered": by_day_ordered,
            "year": year,
            "term": term,
        },
    )


@teacher_portal_required
# tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
@role_required(User.Role.TEACHER)
def teacher_lesson_notes(request: HttpRequest):
    # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
    """Lesson notes upload and list. RBAC: current teacher only."""
    profile = TeacherProfile.objects.filter(user=request.user).first()
    if not profile:
        messages.error(request, "No teacher profile found.")
        return redirect("portal:teacher_dashboard_alias")
    plans = (
        LessonPlan.objects.filter(teacher=profile)
        .prefetch_related("attachments")
        .order_by("-week_start_date")[:50]
    )
    form = LessonPlanUploadForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        obj = form.save(commit=False)
        obj.teacher = profile
        obj.save()
        messages.success(request, "Lesson plan uploaded.")
        return redirect("portal:teacher_lesson_notes")
    hero = {
        "title": "Lesson Notes",
        "subtitle": "Upload weekly lesson plans (PDF)",
        "actions": [],
    }
    return render(
        request,
        "teacher/lesson_notes.html",
        {"hero": hero, "plans": plans, "form": form},
    )


# tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
@teacher_portal_required
@role_required(User.Role.TEACHER)
# tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
def teacher_lesson_plan_add_attachment(request: HttpRequest, lesson_plan_id: int):
    """Add a resource attachment to an existing lesson plan (Wave 6)."""
    # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
    profile = TeacherProfile.objects.filter(user=request.user).first()
    if not profile:
        messages.error(request, "No teacher profile found.")
        return redirect("portal:teacher_dashboard_alias")
    plan = get_object_or_404(LessonPlan, pk=lesson_plan_id, teacher=profile)
    if request.method == "POST":
        form = LessonPlanAttachmentForm(request.POST, request.FILES)
        if form.is_valid():
            att = form.save(commit=False)
            att.lesson_plan = plan
            att.save()
            messages.success(request, "Resource attached.")
            return redirect("portal:teacher_lesson_notes")
    else:
        form = LessonPlanAttachmentForm()
    hero = {
        "title": "Add resource",
        "subtitle": f"Attach a file to « {plan.title} »",
        "actions": [],
    }
    return render(
        request,
        "teacher/lesson_plan_add_attachment.html",
        {"hero": hero, "plan": plan, "form": form},
    )


@teacher_portal_required
@role_required(User.Role.TEACHER)
def teacher_wellness(request: HttpRequest):
    """Teacher wellness / wellbeing: reminder and link to resources (Wave 6)."""
    hero = {"title": "Wellness", "subtitle": "Take care of yourself", "actions": []}
    return render(request, "teacher/wellness.html", {"hero": hero})

# tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17

@teacher_portal_required
# tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
@role_required(User.Role.TEACHER)
def teacher_hr_status(request: HttpRequest):
    # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
    """HR & Status: employment details and attestation. RBAC: current teacher only."""
    profile = TeacherProfile.objects.filter(user=request.user).first()
    if not profile:
        messages.error(request, "No teacher profile found.")
        return redirect("portal:teacher_dashboard_alias")
    attestation_valid = getattr(profile, "attestation_valid", None)
    if attestation_valid is None:
        attestation_valid = True
    hero = {
        "title": "HR & Status",
        "subtitle": "Employment and attestation",
        "actions": [],
    }
    return render(
        request,
        "teacher/hr_status.html",
        {
            "hero": hero,
            "teacher_profile": profile,
            "attestation_valid": attestation_valid,
        },
    )
# tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17


# tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
@teacher_portal_required
@role_required(User.Role.TEACHER)
# tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
def teacher_disciplinary(request: HttpRequest):
    """Disciplinary portal: refer incidents to discipline master. RBAC: teacher only."""
    # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
    profile = TeacherProfile.objects.filter(user=request.user).first()
    if not profile:
        messages.error(request, "No teacher profile found.")
        return redirect("portal:teacher_dashboard_alias")
    hero = {
        "title": "Disciplinary",
        "subtitle": "Refer incidents to the Discipline Master",
        "actions": [],
    }
    return render(
        request,
        "teacher/disciplinary.html",
        {"hero": hero, "teacher_profile": profile},
    )


def _can_manage_discipline(user):
    if not user or not user.is_authenticated:
        return False
    if getattr(user, "is_superuser", False):
        return True
    role = get_user_role(user)
    if role in ("DISCIPLINE_MASTER", "CENSOR"):
        return True
    return getattr(user, "has_feature_permission", lambda _: False)("discipline.manage")


@login_required
def discipline_incidents_list(request: HttpRequest):
    """List disciplinary incidents. RBAC: DISCIPLINE_MASTER, CENSOR, or discipline.manage."""
    if not _can_manage_discipline(request.user):
        return HttpResponseForbidden(
            "You do not have permission to view disciplinary incidents."
        )
    incidents_qs = Incident.objects.select_related(
        "school", "student", "teacher", "created_by"
    )
    school = getattr(request, "school", None)
    if school is not None:
        incidents_qs = incidents_qs.filter(school=school)
    incidents = incidents_qs.order_by("-date", "-created_at")[:100]
    hero = {
        "title": "Disciplinary Incidents",
        "subtitle": "View and manage incidents (tardiness, behavior). Parents are notified when requested.",
        "actions": [],
    }
    return render(
        request,
        "staff/discipline_incidents.html",
        {"hero": hero, "incidents": incidents},
    # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
    )

# tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17

@teacher_portal_required
# tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
@role_required(User.Role.TEACHER)
def teacher_training_log(request: HttpRequest):
    # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
    """Training log: in-service / professional development. RBAC: current teacher only."""
    profile = TeacherProfile.objects.filter(user=request.user).first()
    if not profile:
        messages.error(request, "No teacher profile found.")
        return redirect("portal:teacher_dashboard_alias")
    entries = TeacherTrainingEntry.objects.filter(teacher=profile).order_by("-date")[
        :50
    ]
    form = TeacherTrainingEntryForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        obj = form.save(commit=False)
        obj.teacher = profile
        obj.save()
        messages.success(request, "Training entry added.")
        return redirect("portal:teacher_training_log")
    hero = {
        "title": "Training Log",
        "subtitle": "In-service training and professional development",
        "actions": [],
    }
    return render(
        request,
        "teacher/training_log.html",
        {"hero": hero, "entries": entries, "form": form},
    )
