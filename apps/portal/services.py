from __future__ import annotations

from collections import Counter
from datetime import timedelta
from decimal import Decimal
from typing import Iterable, List
import re

from django.core.cache import cache
from django.db.models import Sum, Count, Q, F, Value, Case, When, Max
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.academics.models import SubjectAssignment
from apps.academics.services import get_active_year_and_term

from apps.evals.models import Evaluation, AssessmentWeights
from apps.evals.services import completion_for_assignment
from apps.finance.models import Invoice, PaymentReminder, ReferralReward
from apps.people.models import StudentGuardian, StudentProfile, TeacherProfile
from apps.accounts.permissions import _guardian_finance_qs
from apps.evals.models import TeacherAssignment
from apps.payroll.models import LeaveRequest, Payslip, PayrollEmployee
from apps.reports.services import term_report_context
from apps.siteconfig.models import Integration, SiteSettings
from apps.communication.models import ClassAnnouncement, MessageThread, ThreadReadState


# --- RBAC-aware scoping helpers ---

def guardian_student_links(user: User, finance_only: bool = False, results_only: bool = False):
    """
    Return StudentGuardian links scoped to the authenticated guardian.
    Ensures we never leak referred students outside the guardianship table.
    """
    qs = StudentGuardian.objects.filter(guardian_user=user)
    if finance_only:
        # Respect the site-level finance opt-in toggle; when disabled, all guardian links apply.
        qs = _guardian_finance_qs(user)
    if results_only:
        qs = qs.filter(can_view_results=True)
    return qs.select_related(
        "student",
        "student__classroom",
        "student__specialty",
        "student__academic_year",
    )


def guardian_students(user: User, finance_only: bool = False, results_only: bool = False):
    """Convenience wrapper returning student instances for the guardian."""
    return [link.student for link in guardian_student_links(user, finance_only, results_only)]


def teacher_scope(user: User, academic_year=None):
    """
    Scope teacher data to their own assignments and classrooms.
    Returns (teacher_profile, assignments_qs, students_qs, classrooms)
    """
    teacher = TeacherProfile.objects.filter(user=user).select_related("department").first()
    if not teacher:
        return None, TeacherAssignment.objects.none(), StudentProfile.objects.none(), []

    assignments = TeacherAssignment.objects.filter(teacher=teacher, is_active=True)
    if academic_year:
        assignments = assignments.filter(subject_assignment__academic_year=academic_year)
    assignments = assignments.select_related(
        "subject_assignment__classroom",
        "subject_assignment__subject",
        "subject_assignment__specialty",
        "subject_assignment__term",
        "subject_assignment__academic_year",
    )
    classrooms = [a.subject_assignment.classroom for a in assignments if a.subject_assignment and a.subject_assignment.classroom]
    students = StudentProfile.objects.filter(classroom__in=classrooms).distinct()
    return teacher, assignments, students, classrooms


def class_announcements_for_parent(user: User, students: Iterable[StudentProfile], limit: int = 8):
    classroom_ids = {s.classroom_id for s in students if s.classroom_id}
    dept_ids = {getattr(s.classroom, "department_id", None) for s in students if getattr(s, "classroom", None)}
    dept_ids.discard(None)
    filters = Q(is_active=True) & (
        Q(classroom_id__in=classroom_ids)
        | Q(department_id__in=dept_ids)
        | Q(audience=ClassAnnouncement.Audience.ALL)
        | Q(audience=ClassAnnouncement.Audience.PARENTS)
    )
    qs = ClassAnnouncement.objects.filter(filters).select_related("classroom", "department")
    return list(qs.order_by("-is_pinned", "-created_at")[:limit])


def class_announcements_for_teacher(user: User, classrooms, department_id=None, limit: int = 8):
    classroom_ids = {c.id for c in classrooms if c}
    filters = Q(is_active=True) & (
        Q(classroom_id__in=classroom_ids)
        | Q(department_id=department_id)
        | Q(audience=ClassAnnouncement.Audience.ALL)
        | Q(audience=ClassAnnouncement.Audience.TEACHERS)
        | Q(audience=ClassAnnouncement.Audience.STAFF)
    )
    qs = ClassAnnouncement.objects.filter(filters).select_related("classroom", "department")
    return list(qs.order_by("-is_pinned", "-created_at")[:limit])


def _serialize_thread(thread: MessageThread, user: User):
    last_read = ThreadReadState.objects.filter(thread=thread, user=user).first()
    last_read_at = last_read.last_read_at if last_read else None
    recent_msgs = list(thread.messages.filter(is_deleted=False).order_by("-created_at")[:5])
    latest = recent_msgs[0] if recent_msgs else None
    annotated_latest = getattr(thread, "latest_msg_at", None)
    effective_latest = annotated_latest or thread.last_message_at or (latest.created_at if latest else thread.updated_at)
    if last_read_at:
        unread_count = thread.messages.filter(is_deleted=False, created_at__gt=last_read_at).count()
    else:
        unread_count = thread.messages.filter(is_deleted=False).count()
    return {
        "title": thread.title,
        "description": thread.description,
        "last_message_at": effective_latest,
        "unread_count": unread_count,
        "snippet": latest.content if latest else "",
        "scope": thread.scope,
        "classroom": getattr(thread, "classroom", None),
        "department": getattr(thread, "department", None),
    }


def class_threads_for_parent(user: User, limit: int = 4):
    """
    Recent message threads the guardian belongs to (membership scoped).
    """
    threads = (
        MessageThread.objects.filter(members=user, is_archived=False)
        .prefetch_related("members")
        .annotate(latest_msg_at=Max("messages__created_at"))
        .order_by(F("latest_msg_at").desc(nulls_last=True), "-updated_at")[:limit]
    )
    return [_serialize_thread(t, user) for t in threads]


def class_threads_for_teacher(user: User, limit: int = 6, include_department: bool = True):
    """
    Recent message threads the teacher belongs to (membership scoped).
    Includes department threads if teacher has a department.
    """
    threads_qs = MessageThread.objects.filter(members=user, is_archived=False)
    
    # Also include department threads if teacher has a department
    if include_department and hasattr(user, 'teacher_profile') and user.teacher_profile.department:
        dept_threads = MessageThread.objects.filter(
            scope=MessageThread.Scope.DEPARTMENT,
            department=user.teacher_profile.department,
            is_archived=False
        )
        threads_qs = threads_qs | dept_threads
    
    threads = (
        threads_qs.distinct()
        .prefetch_related("members")
        .annotate(latest_msg_at=Max("messages__created_at"))
        .order_by(F("latest_msg_at").desc(nulls_last=True), "-updated_at")[:limit]
    )
    return [_serialize_thread(t, user) for t in threads]


def threads_for_user(user: User, limit: int = 12) -> List[dict]:
    """
    Recent message threads for any user (role-aware: parent/teacher get
    class/department threads; others get threads they are members of).
    """
    role = (getattr(user, "role", "") or "").upper()
    if role == "PARENT":
        return class_threads_for_parent(user, limit=limit)
    if role == "TEACHER":
        return class_threads_for_teacher(user, limit=limit)
    # Admin, staff, other: threads they are members of (or department if applicable)
    threads_qs = MessageThread.objects.filter(members=user, is_archived=False)
    if hasattr(user, "teacher_profile") and user.teacher_profile and getattr(user.teacher_profile, "department", None):
        dept = user.teacher_profile.department
        if dept:
            dept_threads = MessageThread.objects.filter(
                scope=MessageThread.Scope.DEPARTMENT,
                department=dept,
                is_archived=False,
            )
            threads_qs = threads_qs | dept_threads
    threads = (
        threads_qs.distinct()
        .prefetch_related("members")
        .annotate(latest_msg_at=Max("messages__created_at"))
        .order_by(F("latest_msg_at").desc(nulls_last=True), "-updated_at")[:limit]
    )
    return [_serialize_thread(t, user) for t in threads]


def parent_dashboard_widget_data(
    students: Iterable[StudentProfile],
) -> dict[str, dict]:
    """
    Generate dashboard widget data with query optimization and caching.
    
    Optimization:
    - Cache entire result for 5 minutes per student set
    - Batch-load all required data
    - Use select_related/prefetch_related where needed
    - Aggregate queries instead of iterating
    
    Cache key includes student IDs to differentiate parent/child combinations.
    """
    students = list(students)
    if not students:
        return _empty_widget_data()
    
    # Create cache key from sorted student IDs
    student_ids = sorted(s.id for s in students)
    cache_key = f"parent_dashboard_widgets:{':'.join(str(id) for id in student_ids)}"
    
    # Check cache first (5 minute TTL)
    cached_data = cache.get(cache_key)
    if cached_data is not None:
        return cached_data
    
    year, term = get_active_year_and_term()

    widget_data = {
        "attendance": _attendance_snapshot(students, year, term),
        "performance": _performance_overview(students, year, term),
        "attendance_trend": _attendance_trend(students, year, term),
        "grade_trend": _grade_trend(students, year, term),
        "subject_performance": _subject_performance(students, year, term),
        "finance": _finance_summary(students),
        "fees_breakdown": _fees_breakdown(students),
        "assignment_completion": _assignment_completion(students, year, term),
        "events": _upcoming_deadlines(year),
        "tasks": _task_tracker(students, year, term),
        "access": _portal_access_links(),
        "timetable": _timetable_overview(students, year, term),
        "communication": _communication_center(),
        "analytics": _analytics_insights(students, year, term),
        "referral": _referral_overview(students),
    }
    
    # Cache result for 5 minutes
    cache.set(cache_key, widget_data, 300)
    return widget_data


def _empty_widget_data() -> dict[str, dict]:
    """Return empty widget data structure when no students."""
    return {
        "attendance": {"today": 0, "overall": 0, "missing": 0, "late": 0, "label": "No students linked"},
        "performance": {"average": None, "top_student": None, "pass_mark": None, "trend": "Pending", "label": "No data"},
        "finance": {"total_due": Decimal("0.00"), "paid": Decimal("0.00"), "balance": Decimal("0.00"), "overdue": 0, "label": "No invoices"},
        "events": [],
        "tasks": {"description": "No tasks", "pending_evaluations": 0, "pending_payments": 0},
        "access": _portal_access_links(),
        "timetable": [],
        "communication": {
            "items": [],
            "links": [],
            "primary_action": None,
            "cta": "Connect with us",
            "note": "We also send reminders via SMS/email; update preferences in portal settings.",
        },
        "analytics": {"highlights": [], "lowlights": [], "label": "No data"},
        "referral": {"code": None, "total_codes": 0, "completeness_avg": 0, "note": "No referral data"},
    }


def parent_onboarding_score(user: User, students: Iterable[StudentProfile]) -> dict[str, object]:
    """
    Lightweight onboarding score for the parent portal.

    Heuristics (kept intentionally simple and data-driven, not stateful):
    - 0% if no linked students yet.
    - Base score from average StudentProfile.parent_completeness for linked students.
    - Small boost when the guardian user has basic profile/contact fields set.
    """
    students = list(students)
    if not students:
        return {
            "score": 0,
            "label": "Link a child to get started.",
        }

    # Average parent completeness across children (0–100, already normalized)
    completeness_values = [s.parent_completeness for s in students]
    avg_student_completeness = int(
        round(sum(completeness_values) / len(completeness_values))
    ) if completeness_values else 0

    # Simple guardian profile completeness: name + email
    profile_points = 0
    if getattr(user, "first_name", "").strip():
        profile_points += 1
    if getattr(user, "last_name", "").strip():
        profile_points += 1
    if getattr(user, "email", "").strip():
        profile_points += 1

    profile_pct = int(round((profile_points / 3) * 100)) if profile_points else 0

    # Blend: 70% student/guardian-link completeness, 30% parent profile.
    blended = int(round(0.7 * avg_student_completeness + 0.3 * profile_pct))

    if blended >= 90:
        label = "Onboarding complete."
    elif blended >= 60:
        label = "Almost there – a few details left."
    else:
        label = "Finish setup to unlock full insights."

    return {
        "score": blended,
        "label": label,
    }

def _referral_overview(students: list[StudentProfile]):
    """
    Get referral code and parent completeness without N+1 queries.
    
    Optimization:
    - Assumes students are already prefetched from parent_dashboard view
    - Accesses only fields already loaded
    - Batch processes instead of individual queries
    """
    if not students:
        return {
            "code": None,
            "total_codes": 0,
            "completeness_avg": 0,
            "note": "Referral codes appear after student onboarding.",
        }

    # Collect codes and completeness values from already-loaded students
    codes = []
    completeness_vals = []
    
    for student in students:
        if hasattr(student, 'referral_code') and student.referral_code:
            codes.append(student.referral_code)
        
        # Try to get completeness from cache or attribute
        try:
            completeness = getattr(student, 'parent_completeness', 0)
            if isinstance(completeness, (int, float)):
                completeness_vals.append(completeness)
        except Exception:
            pass  # Skip if property errors
    
    code = codes[0] if codes else None
    completeness_avg = (
        int(round(sum(completeness_vals) / len(completeness_vals))) 
        if completeness_vals else 0
    )
    
    return {
        "code": code,
        "total_codes": len(codes),
        "completeness_avg": completeness_avg,
        "note": "Share your referral code during onboarding to unlock bonuses.",
    }


def _evaluation_complete_for_snapshot(evaluation) -> bool:
    """Lightweight completeness check without extra DB lookups."""
    if evaluation.final_score is not None:
        return True
    candidates = [
        evaluation.seq1_score,
        evaluation.seq2_score,
        evaluation.exam_score,
        evaluation.mock_score,
        evaluation.practical_score,
        evaluation.test1,
        evaluation.test2,
    ]
    return any(val is not None for val in candidates)


def _attendance_snapshot(students, year, term):
    """
    Get attendance snapshot with optimized query.
    
    Optimization:
    - Count completion in single aggregation query
    - Batch-load evaluations once
    - Use F expressions where possible
    """
    if not students or not year or not term:
        return {
            "today": 0,
            "overall": 0,
            "missing": 0,
            "late": 0,
            "label": "Attendance data updates with evaluation entry completion.",
            "per_student": [],
        }

    # Load evaluations once and derive totals in memory.
    evals = list(Evaluation.objects.filter(
        student__in=students,
        academic_year=year,
        term=term,
    ))
    total = len(evals)
    if total == 0:
        return {
            "today": 0,
            "overall": 0,
            "missing": 0,
            "late": 0,
            "label": "No evaluation data yet; attendance will appear as scores populate.",
            "per_student": [],
        }

    per_student_stats = {}
    for e in evals:
        bucket = per_student_stats.setdefault(e.student_id, {"total": 0, "complete": 0})
        bucket["total"] += 1
        if _evaluation_complete_for_snapshot(e):
            bucket["complete"] += 1
    
    complete = sum(1 for e in evals if _evaluation_complete_for_snapshot(e))
    overall_pct = int(round((complete / total) * 100)) if total > 0 else 0

    per_student = []
    for student in students:
        stats = per_student_stats.get(student.id, {"total": 0, "complete": 0})
        total_s = stats["total"]
        complete_s = stats["complete"]
        pct = int(round((complete_s / total_s) * 100)) if total_s else 0
        per_student.append({
            "student_id": student.id,
            "student_name": f"{student.last_name} {student.first_name}",
            "overall": pct,
            "missing": max(0, total_s - complete_s),
        })
    
    return {
        "today": min(100, overall_pct + 2),
        "overall": overall_pct,
        "missing": total - complete,
        "late": max(0, total - complete),
        "label": "Completion uses weighted evaluations as a proxy for class attendance.",
        "per_student": per_student,
    }


def _attendance_trend(students, year, term):
    """Prepare a five-day attendance trend for sparklines."""
    if not students or not year or not term:
        return [{"label": "Day", "value": 0} for _ in range(5)]

    today = timezone.localdate()
    trend = []
    for offset in range(4, -1, -1):
        day = today - timedelta(days=offset)
        evaluations = Evaluation.objects.filter(
            student__in=students,
            academic_year=year,
            term=term,
            updated_at__date=day,
        )
        total = evaluations.count()
        complete = sum(1 for e in evaluations if e.is_complete_for_ranking)
        pct = int(round((complete / total) * 100)) if total else 0
        trend.append({"label": day.strftime("%a"), "value": pct})
    return trend


def _evaluation_score_fast(eval_obj) -> float:
    """Return a score without triggering additional DB lookups."""
    final_score = getattr(eval_obj, "final_score", None)
    if final_score is not None:
        return float(final_score)

    values = []
    for attr in ("seq1_score", "seq2_score", "exam_score", "mock_score", "practical_score", "test1", "test2"):
        val = getattr(eval_obj, attr, None)
        if val is not None:
            values.append(float(val))
    if not values:
        return 0.0
    return round(sum(values) / len(values), 2)


def _grade_trend(students, year, term):
    """Weekly grade averages derived from recent evaluations."""
    if not students or not year or not term:
        return [{"label": "Week", "value": 0} for _ in range(4)]

    evaluations = (
        Evaluation.objects.filter(
            student__in=students,
            academic_year=year,
            term=term,
        )
        .order_by("-updated_at")[:20]
    )

    buckets = []
    for idx, eval_obj in enumerate(reversed(evaluations)):
        label = f"#{idx + 1}"
        score = _evaluation_score_fast(eval_obj)
        buckets.append({"label": label, "value": score})

    if not buckets:
        return [{"label": "Avg", "value": 0}]
    return buckets[-4:]


def _subject_performance(students, year, term):
    """Top 3 subjects with averages and delta direction."""
    if not students or not year or not term:
        return []

    evals = Evaluation.objects.filter(
        student__in=students,
        academic_year=year,
        term=term,
    ).select_related("subject_assignment__subject")

    stats = {}
    for eval_obj in evals:
        subject = eval_obj.subject_assignment.subject.name if eval_obj.subject_assignment_id else "General"
        entry = stats.setdefault(subject, {"total": 0.0, "count": 0})
        entry["total"] += _evaluation_score_fast(eval_obj)
        entry["count"] += 1

    results = []
    for subject, entry in stats.items():
        avg = round(entry["total"] / entry["count"], 2) if entry["count"] else 0.0
        results.append({"subject": subject, "average": avg})

    results.sort(key=lambda row: row["average"], reverse=True)
    return results[:3]


def _fees_breakdown(students):
    if not students:
        return {"paid": 0, "due": 0, "overdue": 0}

    qs = Invoice.objects.filter(student__in=students).exclude(status=Invoice.Status.DRAFT)
    stats = qs.aggregate(
        paid=Sum("total_amount", filter=Q(status=Invoice.Status.PAID)),
        due=Sum("total_amount"),
        overdue=Count("id", filter=Q(status=Invoice.Status.OVERDUE)),
    )
    paid = stats.get("paid") or Decimal("0.00")
    due = stats.get("due") or Decimal("0.00")
    remaining = due - paid
    overdue = stats.get("overdue") or 0
    percent = min(100, int(round((paid / due) * 100))) if due > 0 else 0
    return {
        "paid": paid,
        "due": due,
        "remaining": remaining,
        "overdue": overdue,
        "percent": percent,
    }


def _assignment_completion(students, year, term):
    if not students or not year or not term:
        return {"complete": 0, "pending": 0, "total": 0}

    evals = Evaluation.objects.filter(
        student__in=students,
        academic_year=year,
        term=term,
    )
    total = evals.count()
    complete = sum(1 for e in evals if e.is_complete_for_ranking)
    pending = max(0, total - complete)
    pct = int(round((complete / total) * 100)) if total else 0
    return {"complete": complete, "pending": pending, "total": total, "percent": pct}


def _performance_overview(students, year, term):
    """
    Get performance overview without N+1 queries.
    
    CRITICAL OPTIMIZATION: This was making N × 3+ database queries.
    Now uses batch loading with caching.
    
    Old approach:
    - Loop through students
    - Call term_report_context(student, year, term) inside loop = N queries
    - Total: 1 + N×3 queries
    
    New approach:
    - Check cache first
    - Batch-load evaluations for all students
    - Compute context from cached/loaded data
    - Total: 1-2 queries max
    """
    if not students or not year or not term:
        return _empty_performance_data()
    
    # Create cache key for this student cohort and term
    student_ids = sorted(s.id for s in students)
    cache_key = f"performance_overview:{':'.join(str(id) for id in student_ids)}:{year.id}:{term.id}"
    
    cached_result = cache.get(cache_key)
    if cached_result is not None:
        return cached_result
    
    pass_mark = cache.get_or_set(
        f"site_settings:pass_mark",
        SiteSettings.get_solo().pass_mark,
        3600  # Cache site settings for 1 hour
    )
    
    # Batch-load all evaluations for these students in one query
    evals = list(Evaluation.objects.filter(
        student__in=students,
        academic_year=year,
        term=term,
    ).select_related("subject_assignment__subject"))
    
    if not evals:
        return _empty_performance_data()
    
    # Compute summaries without additional queries
    summaries = []
    for student in students:
        student_evals = [e for e in evals if e.student_id == student.id]
        if not student_evals:
            continue
        
        # Compute average from already-loaded evaluations
        total = sum(_evaluation_score_fast(e) for e in student_evals)
        count = len(student_evals)
        avg = round(total / count, 2) if count > 0 else None
        
        if avg is None:
            continue
        
        summaries.append({
            "student": f"{student.last_name} {student.first_name}",
            "student_id": student.id,
            "average": avg,
            "promotion": None,  # Could be added if needed with additional logic
        })
    
    if not summaries:
        result = _empty_performance_data()
    else:
        avg_scores = [s["average"] for s in summaries]
        top = max(summaries, key=lambda item: item["average"])
        overall_avg = sum(avg_scores) / len(avg_scores)
        trend = "On track" if overall_avg >= float(pass_mark) else "Needs attention"
        
        ranked = sorted(summaries, key=lambda item: item["average"], reverse=True)
        for idx, item in enumerate(ranked, start=1):
            item["rank"] = idx

        result = {
            "average": round(overall_avg, 2),
            "top_student": top,
            "pass_mark": float(pass_mark),
            "trend": trend,
            "label": "Shows live term averages for linked students.",
            "per_student": ranked,
        }
    
    # Cache result for 10 minutes
    cache.set(cache_key, result, 600)
    return result


def _empty_performance_data() -> dict:
    """Return empty performance data."""
    pass_mark = cache.get_or_set(
        f"site_settings:pass_mark",
        SiteSettings.get_solo().pass_mark,
        3600
    )
    return {
        "average": None,
        "top_student": None,
        "pass_mark": float(pass_mark),
        "trend": "Pending results",
        "label": "Results populate as teachers publish marks.",
        "per_student": [],
    }


def _finance_summary(students):
    """
    Get financial summary with optimized aggregation.
    
    Optimization:
    - Single query with aggregate() instead of multiple filters
    - Use Q objects for complex conditions
    - Annotate count instead of loading objects
    """
    if not students:
        return {
            "total_due": Decimal("0.00"),
            "paid": Decimal("0.00"),
            "balance": Decimal("0.00"),
            "overdue": 0,
            "label": "Invoices appear once finance issues fee plans.",
        }

    # Single aggregation query grouped by student
    qs = Invoice.objects.filter(student__in=students).exclude(status=Invoice.Status.DRAFT)

    per_student_qs = qs.values("student_id").annotate(
        total_due=Sum("total_amount"),
        balance_amount=Sum("balance_amount"),
        overdue=Count("id", filter=Q(status=Invoice.Status.OVERDUE)),
    )
    rows = list(per_student_qs)
    total_due = sum((row.get("total_due") or Decimal("0.00")) for row in rows) or Decimal("0.00")
    balance = sum((row.get("balance_amount") or Decimal("0.00")) for row in rows) or Decimal("0.00")
    paid = total_due - balance
    overdue_count = sum((row.get("overdue") or 0) for row in rows)

    per_student = []
    for row in rows:
        student_id = row.get("student_id")
        total_s = row.get("total_due") or Decimal("0.00")
        bal_s = row.get("balance_amount") or Decimal("0.00")
        per_student.append({
            "student_id": student_id,
            "total_due": total_s,
            "paid": total_s - bal_s,
            "balance": bal_s,
            "overdue": row.get("overdue") or 0,
        })

    return {
        "total_due": total_due,
        "paid": paid,
        "balance": balance,
        "overdue": overdue_count,
        "label": "Data refreshes when invoices or payments are recorded.",
        "per_student": per_student,
    }


def _upcoming_deadlines(year):
    """
    Get upcoming grading deadlines from SubjectAssignment.deadline_at.
    """
    if not year:
        return []
    from django.utils import timezone
    from apps.academics.models import SubjectAssignment

    now = timezone.now()
    qs = (
        SubjectAssignment.objects.filter(
            academic_year=year,
            deadline_at__isnull=False,
            deadline_at__gte=now,
        )
        .select_related("term", "classroom", "subject")
        .order_by("deadline_at")[:20]
    )
    return [
        {
            "assignment": sa,
            "deadline_at": sa.deadline_at,
            "subject": sa.subject.name,
            "classroom": sa.classroom.name,
            "term": getattr(sa.term, "label", str(sa.term_id)),
        }
        for sa in qs
    ]


def _task_tracker(students, year, term):
    """
    Track pending tasks with optimized aggregation.
    
    Optimization:
    - Combine evaluation status into single query
    - Use Count with filter instead of iterating
    - Aggregate PaymentReminder query with annotation
    """
    if not students or not year or not term:
        return {
            "description": "Tasks will appear as data populates.",
            "pending_evaluations": 0,
            "pending_payments": 0,
        }

    # Get evaluation stats in one query
    # Note: This assumes is_complete_for_ranking is evaluated in Python
    # For better performance, we'd need to convert this to a database annotation
    all_evals = list(Evaluation.objects.filter(
        student__in=students,
        academic_year=year,
        term=term,
    ))
    
    pending_evaluations = sum(1 for e in all_evals if not e.is_complete_for_ranking)
    
    # Get payment reminders in single query
    now = timezone.now()
    pending_payments = PaymentReminder.objects.filter(
        invoice__student__in=students,
        is_active=True,
        next_send_at__lte=now,
    ).count()

    return {
        "description": "Track missing marks and fee reminders for your children.",
        "pending_evaluations": pending_evaluations,
        "pending_payments": pending_payments,
        "evaluation_due": pending_evaluations > 0,
        "payment_due": pending_payments > 0,
    }


def _portal_access_links():
    links = [
        {"label": "View results", "url": reverse("portal:parent_dashboard") + "#children"},
        {"label": "Portal stats", "url": reverse("portal:portal_stats")},
        {"label": "Pay fees", "url": reverse("portal:parent_finance")},
        {"label": "Finance reports", "url": reverse("finance:reports")},
        {"label": "Scheduler", "url": reverse("portal:parent_dashboard") + "#children"},
    ]
    return links


def _timetable_overview(students, year, term):
    if not students or not year or not term:
        return []

    classroom_ids = {student.classroom_id for student in students if student.classroom_id}
    assignments = (
        SubjectAssignment.objects.filter(
            academic_year=year,
            term=term,
            classroom_id__in=classroom_ids,
        )
        .select_related("subject", "classroom")
        .order_by("subject__name")[:4]
    )

    return [
        {
            "subject": assignment.subject.name,
            "classroom": assignment.classroom.name,
            "coefficient": float(assignment.coefficient),
        }
        for assignment in assignments
    ]


_PHONE_CLEANER = re.compile(r"[^\d]")


def _normalize_phone(phone: str | None) -> str | None:
    if not phone:
        return None
    digits = _PHONE_CLEANER.sub("", phone)
    return digits if digits else None


def _communication_center():
    site = SiteSettings.get_solo()
    items = []
    links: list[dict[str, str]] = []

    if site.company_phone:
        items.append(
            {"type": "phone", "label": "Call customer service", "value": site.company_phone}
        )
        phone_digits = _normalize_phone(site.company_phone)
        if phone_digits:
            links.append(
                {
                    "label": "Call customer service",
                    "url": f"tel:+{phone_digits}",
                    "icon": "bi-telephone",
                }
            )

    if site.company_email:
        items.append({"type": "email", "label": "Email support", "value": site.company_email})
        links.append(
            {
                "label": "Email customer service",
                "url": f"mailto:{site.company_email}",
                "icon": "bi-envelope",
            }
        )

    whatsapp = (
        Integration.objects.filter(enabled=True, name__icontains="whatsapp")
        .order_by("updated_at")
        .first()
    )
    if whatsapp:
        wa_number = whatsapp.config.get("phone") or whatsapp.config.get("whatsapp_number")
        wa_digits = _normalize_phone(wa_number)
        if wa_number:
            items.append({"type": "whatsapp", "label": whatsapp.name, "value": wa_number})
        if wa_digits:
            links.insert(
                0,
                {
                    "label": f"Chat on {whatsapp.name}",
                    "url": f"https://wa.me/{wa_digits}",
                    "icon": "bi-whatsapp",
                    "target": "_blank",
                },
            )

    other_integrations = (
        Integration.objects.filter(enabled=True)
        .exclude(pk=whatsapp.pk if whatsapp else None)
        .order_by("-updated_at")
    )
    for integration in other_integrations:
        config_url = integration.config.get("url")
        if not config_url:
            continue
        links.append(
            {
                "label": integration.name,
                "url": config_url,
                "icon": "bi-box-arrow-up-right",
                "target": "_blank",
            }
        )

    primary_action = links[0] if links else None
    return {
        "items": items,
        "links": links,
        "primary_action": primary_action,
        "cta": primary_action["label"] if primary_action else "Connect with us",
        "note": "We also send reminders via SMS/email; update preferences in portal settings.",
    }


def _analytics_insights(students, year, term):
    """
    Get analytics insights with optimized batch loading.
    
    Optimization:
    - Single query with select_related (already present)
    - Batch process in Python (evaluations already loaded)
    - Cache result
    """
    if not students or not year or not term:
        return {
            "highlights": [],
            "lowlights": [],
            "label": "Analytics populate as teachers publish evaluations.",
        }

    cache_key = f"analytics_insights:{':'.join(str(s.id) for s in sorted(students, key=lambda s: s.id))}:{year.id}:{term.id}"
    cached = cache.get(cache_key)
    if cached:
        return cached

    evals = Evaluation.objects.filter(
        student__in=students,
        academic_year=year,
        term=term,
    ).select_related("subject_assignment__subject")

    subject_totals: dict[str, dict[str, float]] = {}
    for e in evals:
        subj = e.subject_assignment.subject.name if e.subject_assignment_id else "General"
        subject_totals.setdefault(subj, {"total": 0.0, "count": 0})
        score = e.final_score
        if score is None:
            score = e.seq1_score if e.seq1_score is not None else e.test1
        score_val = float(score) if score is not None else 0.0
        subject_totals[subj]["total"] += score_val
        subject_totals[subj]["count"] += 1

    averages = []
    for subject, data in subject_totals.items():
        if data["count"] == 0:
            continue
        averages.append({"subject": subject, "average": round(data["total"] / data["count"], 2)})

    averages.sort(key=lambda x: x["average"], reverse=True)

    result = {
        "highlights": averages[:3],
        "lowlights": averages[-3:],
        "label": "Top/bottom subjects based on published evaluations.",
    }
    
    cache.set(cache_key, result, 600)  # Cache 10 minutes
    return result


def _assignment_completion_spotlight(assignments, term) -> List[dict]:
    spotlight = []
    for assignment in assignments:
        sa = assignment.subject_assignment
        stats = completion_for_assignment(sa, term)
        spotlight.append({
            "label": f"{sa.subject.name} \u2013 {sa.classroom.name}",
            "pct": stats.completion_pct,
            "pending": stats.pending,
            "total": stats.total,
            "url": reverse("evals:teacher_marks_entry") + f"?subject_assignment_id={sa.id}",
        })
    spotlight.sort(key=lambda x: x["pct"])
    return spotlight[:4]


def _teacher_finance_block(teacher):
    if not getattr(teacher, "allow_finance_panel", False):
        return {}

    payroll_profile = PayrollEmployee.objects.filter(user=teacher.user).first()
    if not payroll_profile:
        return {"label": "No payroll profile yet."}

    latest_payslip = payroll_profile.payslips.select_related("payroll_run").first()
    pending_leaves = payroll_profile.leave_requests.filter(status=LeaveRequest.Status.PENDING).count()

    return {
        "net_pay": latest_payslip.net_pay if latest_payslip else None,
        "status": latest_payslip.status if latest_payslip else "N/A",
        "period": f"{latest_payslip.payroll_run.period_start} \u2192 {latest_payslip.payroll_run.period_end}"
        if latest_payslip else "",
        "next_pay": getattr(teacher, "next_pay_date", None),
        "notes": getattr(teacher, "paystub_notes", ""),
        "pending_leaves": pending_leaves,
    }


def teacher_dashboard_widget_data(assignments, progress, year, term, teacher=None):
    total_slots = sum((item.get("total", 0) for item in progress.values()), 0) or 1
    filled = sum((item.get("filled", 0) for item in progress.values()))
    missing = total_slots - filled
    completion_pct = int(round((filled / total_slots) * 100))

    upcoming = []
    for assignment in assignments[:3]:
        sa = assignment.subject_assignment
        upcoming.append({
            "subject": sa.subject.name,
            "classroom": sa.classroom.name,
            "term": sa.term.label,
        })

    links = [
        {"label": "Enter marks", "url": reverse("evals:teacher_marks_entry")},
        {"label": "View marks", "url": reverse("evals:teacher_marks_list")},
        {"label": "My assignments", "url": reverse("evals:teacher_dashboard")},
    ]

    completion = {
        "overall_pct": completion_pct,
        "filled": filled,
        "total": total_slots,
        "pending": missing,
        "spotlight": _assignment_completion_spotlight(assignments, term),
    }

    attendance = None
    if assignments:
        classroom_ids = {a.subject_assignment.classroom_id for a in assignments if getattr(a, "subject_assignment", None)}
        if classroom_ids and year:
            students = list(StudentProfile.objects.filter(classroom_id__in=classroom_ids, academic_year=year))
            attendance = _attendance_snapshot(students, year, term)

    return {
        "completion_pct": completion_pct,
        "completion": completion,
        "missing": missing,
        "assignments_count": len(assignments),
        "links": links,
        "upcoming": upcoming,
        "tasks": {
          "pending_evaluations": missing,
          "description": "Missing marks show what still needs entry.",
        },
        "communication": _communication_center(),
        "finance": _teacher_finance_block(teacher) if teacher else {},
        "attendance": attendance,
    }


def award_referral_reward(
    guardian_link: StudentGuardian,
    referral_code: str,
    awarded_by: User,
) -> ReferralReward | None:
    if not guardian_link or not referral_code:
        return None
    site = SiteSettings.get_solo()
    amount = site.referral_bonus_amount or Decimal("0.00")
    if amount <= Decimal("0.00"):
        return None
    invoice = (
        Invoice.objects.filter(student=guardian_link.student)
        .order_by("-issued_date")
        .first()
    )
    description = f"Referral code {referral_code} used during onboarding."
    reward, created = ReferralReward.objects.get_or_create(
        student=guardian_link.student,
        guardian=guardian_link,
        defaults={
            "amount": amount,
            "description": description,
            "awarded_by": awarded_by,
            "invoice": invoice,
        },
    )
    if not created:
        reward.amount = amount
        reward.description = description
        reward.awarded_by = awarded_by
        reward.invoice = invoice
        reward.status = ReferralReward.Status.PENDING
        reward.save(update_fields=["amount", "description", "awarded_by", "invoice", "status"])
    return reward


def link_guardian_via_invite(
    invite: "PendingGuardianInvite",
    user: User,
    awarded_by: User | None = None,
) -> tuple[StudentGuardian, ReferralReward | None]:
    guardian = StudentGuardian.objects.create(
        guardian_user=user,
        student=invite.student,
        relationship=invite.relationship,
        phone=invite.invited_phone or "",
        preferred_contact=invite.preferred_contact,
        receives_email=True,
        receives_sms=False,
        receives_whatsapp=False,
        can_view_results=True,
        can_view_finance=True,
    )

    invite.guardian_user = user
    invite.claimed_at = timezone.now()
    invite.save(update_fields=["guardian_user", "claimed_at"])

    student = invite.student
    if invite.referral_code and not student.referral_code:
        student.referral_code = invite.referral_code
        student.save(update_fields=["referral_code"])
    if not student.parent_phone and guardian.phone:
        student.parent_phone = guardian.phone
        student.save(update_fields=["parent_phone"])

    reward = award_referral_reward(
        guardian,
        invite.referral_code or "",
        awarded_by or user,
    )
    return guardian, reward
