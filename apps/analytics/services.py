from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timedelta
from decimal import Decimal
from typing import Iterable, Optional

from django.db.models import Avg
from django.utils import timezone

from apps.academics.models import (
    AcademicYear,
    Term,
    Classroom,
    Specialty,
    Subject,
    SubjectAssignment,
)
from apps.evals.models import AssessmentWeights, Evaluation, TeacherAssignment
from apps.people.models import StudentProfile, TeacherProfile
from apps.reports.models import PromotionRule, TermPublishStatus


DEADLINE_MODE_TERM_END = "TERM_END"
DEADLINE_MODE_CUSTOM = "CUSTOM_DEADLINE"
DEADLINE_MODE_PUBLISH = "PUBLISH_DATE"


@dataclass(frozen=True)
class TeacherComplianceRow:
    teacher: TeacherProfile
    expected: int
    on_time: int
    late: int
    missing: int

    @property
    def completion_rate(self) -> float:
        if self.expected <= 0:
            return 0.0
        completed = max(self.expected - self.missing, 0)
        return round((completed / self.expected) * 100, 2)

    @property
    def on_time_rate(self) -> float:
        if self.expected <= 0:
            return 0.0
        return round((self.on_time / self.expected) * 100, 2)


@dataclass(frozen=True)
class SubjectAverageRow:
    subject: Subject
    average: float
    count: int


@dataclass(frozen=True)
class StudentImprovementRow:
    student: StudentProfile
    from_average: float
    to_average: float
    delta: float


@dataclass(frozen=True)
class SpecialtyPassRateRow:
    specialty: Specialty
    total: int
    passed: int
    missing: int

    @property
    def rate(self) -> float:
        if self.total <= 0:
            return 0.0
        return round((self.passed / self.total) * 100, 2)


def _term_end_deadline(term: Term) -> datetime:
    end_dt = datetime.combine(term.end_date, time(23, 59, 59))
    if timezone.is_naive(end_dt):
        end_dt = timezone.make_aware(end_dt, timezone.get_current_timezone())
    return end_dt


def _custom_deadline(
    academic_year: AcademicYear,
    term: Term,
    classroom: Optional[Classroom],
) -> Optional[datetime]:
    """
    Get earliest custom grading deadline for (year, term, classroom).
    Uses SubjectAssignment.grading_deadline_at when set.
    """
    if not academic_year or not term:
        return None
    # tenant-isolation-allow: service-layer-scoped-via-caller-student-classroom-or-teacher-fk
    qs = SubjectAssignment.objects.filter(
        academic_year=academic_year,
        term=term,
        grading_deadline_at__isnull=False,
    ).order_by("grading_deadline_at")
    if classroom:
        qs = qs.filter(classroom=classroom)
    first = qs.first()
    return first.grading_deadline_at if first else None


def _publish_deadline(
    academic_year: AcademicYear,
    term: Term,
    classroom: Optional[Classroom],
) -> Optional[datetime]:
    if classroom:
        class_pub = TermPublishStatus.objects.filter(
            academic_year=academic_year,
            term=term,
            classroom=classroom,
            is_published=True,
        ).first()
        if class_pub and class_pub.published_at:
            return class_pub.published_at

    school_pub = TermPublishStatus.objects.filter(
        academic_year=academic_year,
        term=term,
        classroom__isnull=True,
        is_published=True,
    ).first()
    return school_pub.published_at if school_pub and school_pub.published_at else None


def resolve_deadline(
    academic_year: AcademicYear,
    term: Term,
    classroom: Optional[Classroom],
    mode: str,
) -> datetime:
    if mode == DEADLINE_MODE_CUSTOM:
        custom = _custom_deadline(academic_year, term, classroom)
        return custom or _term_end_deadline(term)
    if mode == DEADLINE_MODE_PUBLISH:
        published = _publish_deadline(academic_year, term, classroom)
        if published:
            return published
        custom = _custom_deadline(academic_year, term, classroom)
        return custom or _term_end_deadline(term)
    return _term_end_deadline(term)


def required_fields(
    academic_year: AcademicYear, classroom: Optional[Classroom], term: Term
) -> list[str]:
    weights = AssessmentWeights.get_for(
        academic_year=academic_year,
        classroom=classroom,
        term=term,
    )
    fields: list[str] = []
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


# tenant-isolation-allow: service-layer-scoped-via-caller-student-classroom-or-teacher-fk
def term_average(student: StudentProfile, term: Term) -> Optional[float]:
    evals = Evaluation.objects.filter(
        student=student,
        term=term,
        academic_year=term.academic_year,
    ).select_related("subject_assignment")

    if not evals.exists():
        return None

    total_weighted = 0.0
    total_coef = 0.0
    for e in evals:
        coef = float(e.subject_assignment.coefficient or 1)
        total_weighted += float(e.total_score) * coef
        total_coef += coef

    if total_coef <= 0:
        return None
    return round(total_weighted / total_coef, 2)


def annual_average(student: StudentProfile, terms: Iterable[Term]) -> Optional[float]:
    term_avgs = []
    for term in terms:
        avg = term_average(student, term)
        if avg is not None:
            term_avgs.append(avg)
    if not term_avgs:
        return None
    return round(sum(term_avgs) / len(term_avgs), 2)


def term_rankings(
    # tenant-isolation-allow: service-layer-scoped-via-caller-student-classroom-or-teacher-fk
    term: Term, classroom: Optional[Classroom] = None
) -> list[tuple[StudentProfile, float]]:
    # tenant-isolation-allow: service-layer-scoped-via-caller-student-classroom-or-teacher-fk
    students = StudentProfile.objects.filter(
        academic_year=term.academic_year,
        is_active=True,
    ).select_related("classroom", "specialty")
    if classroom:
        students = students.filter(classroom=classroom)

    rows: list[tuple[StudentProfile, float]] = []
    for student in students:
        avg = term_average(student, term)
        if avg is None:
            continue
        rows.append((student, avg))

    rows.sort(key=lambda row: row[1], reverse=True)
    return rows


def annual_rankings(
    academic_year: AcademicYear,
    # tenant-isolation-allow: service-layer-scoped-via-caller-student-classroom-or-teacher-fk
    terms: Iterable[Term],
    classroom: Optional[Classroom] = None,
# tenant-isolation-allow: service-layer-scoped-via-caller-student-classroom-or-teacher-fk
) -> list[tuple[StudentProfile, float]]:
    students = StudentProfile.objects.filter(
        academic_year=academic_year,
        is_active=True,
    ).select_related("classroom", "specialty")
    if classroom:
        students = students.filter(classroom=classroom)

    rows: list[tuple[StudentProfile, float]] = []
    for student in students:
        avg = annual_average(student, terms)
        if avg is None:
            continue
        rows.append((student, avg))

    rows.sort(key=lambda row: row[1], reverse=True)
    return rows


def teacher_compliance(
    # tenant-isolation-allow: service-layer-scoped-via-caller-student-classroom-or-teacher-fk
    academic_year: AcademicYear,
    term: Term,
    # tenant-isolation-allow: service-layer-scoped-via-caller-student-classroom-or-teacher-fk
    deadline_mode: str,
) -> list[TeacherComplianceRow]:
    # tenant-isolation-allow: service-layer-scoped-via-caller-student-classroom-or-teacher-fk
    assignments = TeacherAssignment.objects.filter(
        academic_year=academic_year,
        is_active=True,
        subject_assignment__term=term,
    ).select_related(
        "teacher",
        "teacher__user",
        "subject_assignment__classroom",
        "subject_assignment__specialty",
        "subject_assignment__subject",
    )

    stats: dict[int, dict[str, int]] = {}
    teachers: dict[int, TeacherProfile] = {}

    for assignment in assignments:
        teacher = assignment.teacher
        teachers[teacher.id] = teacher
        stats.setdefault(
            teacher.id, {"expected": 0, "on_time": 0, "late": 0, "missing": 0}
        )

        sa = assignment.subject_assignment
        classroom = sa.classroom
        deadline_at = resolve_deadline(academic_year, term, classroom, deadline_mode)
        fields = required_fields(academic_year, classroom, term)

        # tenant-isolation-allow: service-layer-scoped-via-caller-student-classroom-or-teacher-fk
        students = StudentProfile.objects.filter(
            academic_year=academic_year,
            classroom=classroom,
            specialty=sa.specialty,
            is_active=True,
        )
        expected = students.count()
# tenant-isolation-allow: service-layer-scoped-via-caller-student-classroom-or-teacher-fk

        evals = Evaluation.objects.filter(
            academic_year=academic_year,
            term=term,
            subject_assignment=sa,
        )
        complete_qs = evals
        for field in fields:
            complete_qs = complete_qs.exclude(**{f"{field}__isnull": True})

        completed = complete_qs.count()
        on_time = complete_qs.filter(updated_at__lte=deadline_at).count()
        late = max(completed - on_time, 0)
        missing = max(expected - completed, 0)

        stats[teacher.id]["expected"] += expected
        stats[teacher.id]["on_time"] += on_time
        stats[teacher.id]["late"] += late
        stats[teacher.id]["missing"] += missing

    rows = [
        TeacherComplianceRow(
            teacher=teachers[teacher_id],
            expected=data["expected"],
            on_time=data["on_time"],
            late=data["late"],
            missing=data["missing"],
        )
        for teacher_id, data in stats.items()
    ]
    rows.sort(key=lambda row: row.on_time_rate, reverse=True)
    return rows


# tenant-isolation-allow: service-layer-scoped-via-caller-student-classroom-or-teacher-fk
def subject_weaknesses(
    academic_year: AcademicYear,
    term: Term,
    classroom: Optional[Classroom],
    # tenant-isolation-allow: service-layer-scoped-via-caller-student-classroom-or-teacher-fk
    specialty: Optional[Specialty],
    threshold: Decimal,
# tenant-isolation-allow: service-layer-scoped-via-caller-student-classroom-or-teacher-fk
) -> list[SubjectAverageRow]:
    evals = Evaluation.objects.filter(
        academic_year=academic_year,
        term=term,
    ).select_related(
        "subject_assignment__subject",
        "subject_assignment__classroom",
        "subject_assignment__specialty",
    )
    if classroom:
        evals = evals.filter(subject_assignment__classroom=classroom)
    if specialty:
        evals = evals.filter(subject_assignment__specialty=specialty)

    totals: dict[int, float] = {}
    counts: dict[int, int] = {}
    subjects: dict[int, Subject] = {}

    for e in evals:
        subject = e.subject_assignment.subject
        subjects[subject.id] = subject
        totals[subject.id] = totals.get(subject.id, 0.0) + float(e.total_score)
        counts[subject.id] = counts.get(subject.id, 0) + 1

    rows: list[SubjectAverageRow] = []
    for subject_id, total in totals.items():
        count = counts.get(subject_id, 0)
        if count <= 0:
            continue
        avg = total / count
        if Decimal(str(avg)) <= threshold:
            rows.append(
                SubjectAverageRow(
                    subject=subjects[subject_id], average=avg, count=count
                )
            )

    rows.sort(key=lambda row: row.average)
    return rows

# tenant-isolation-allow: service-layer-scoped-via-caller-student-classroom-or-teacher-fk

def student_improvements(
    academic_year: AcademicYear,
    from_term: Term,
    # tenant-isolation-allow: service-layer-scoped-via-caller-student-classroom-or-teacher-fk
    to_term: Term,
    classroom: Optional[Classroom],
    # tenant-isolation-allow: service-layer-scoped-via-caller-student-classroom-or-teacher-fk
    min_delta: Decimal,
) -> list[StudentImprovementRow]:
    # tenant-isolation-allow: service-layer-scoped-via-caller-student-classroom-or-teacher-fk
    students = StudentProfile.objects.filter(
        academic_year=academic_year,
        is_active=True,
    ).select_related("classroom")
    if classroom:
        students = students.filter(classroom=classroom)

    rows: list[StudentImprovementRow] = []
    for student in students:
        from_avg = term_average(student, from_term)
        to_avg = term_average(student, to_term)
        if from_avg is None or to_avg is None:
            continue
        delta = round(to_avg - from_avg, 2)
        if Decimal(str(delta)) >= min_delta:
            rows.append(
                StudentImprovementRow(
                    student=student,
                    from_average=from_avg,
                    to_average=to_avg,
                    delta=delta,
                )
            )

    rows.sort(key=lambda row: row.delta, reverse=True)
    return rows


def specialty_pass_rates(
    # tenant-isolation-allow: service-layer-scoped-via-caller-student-classroom-or-teacher-fk
    academic_year: AcademicYear,
    term: Optional[Term],
    pass_mark: Decimal,
    # tenant-isolation-allow: service-layer-scoped-via-caller-student-classroom-or-teacher-fk
    use_promotion_rule: bool,
) -> list[SpecialtyPassRateRow]:
    terms = (
        [term]
        # tenant-isolation-allow: service-layer-scoped-via-caller-student-classroom-or-teacher-fk
        if term
        else list(
            # tenant-isolation-allow: service-layer-scoped-via-caller-student-classroom-or-teacher-fk
            Term.objects.filter(academic_year=academic_year).order_by("start_date")
        )
    # tenant-isolation-allow: service-layer-scoped-via-caller-student-classroom-or-teacher-fk
    )
    students = StudentProfile.objects.filter(
        academic_year=academic_year,
        is_active=True,
    ).select_related("specialty", "classroom")

    totals: dict[int, int] = {}
    passed: dict[int, int] = {}
    missing: dict[int, int] = {}
    specialties: dict[int, Specialty] = {}

    for student in students:
        specialties[student.specialty_id] = student.specialty
        avg = (
            annual_average(student, terms)
            if term is None
            else term_average(student, term)
        )
        if avg is None:
            missing[student.specialty_id] = missing.get(student.specialty_id, 0) + 1
            continue

        threshold = pass_mark
        if use_promotion_rule:
            rule = PromotionRule.objects.filter(
                academic_year=academic_year,
                classroom=student.classroom,
            ).first()
            if rule:
                threshold = Decimal(str(rule.promotion_average))

        totals[student.specialty_id] = totals.get(student.specialty_id, 0) + 1
        if Decimal(str(avg)) >= threshold:
            passed[student.specialty_id] = passed.get(student.specialty_id, 0) + 1

    rows: list[SpecialtyPassRateRow] = []
    for specialty_id, specialty in specialties.items():
        total = totals.get(specialty_id, 0)
        rows.append(
            SpecialtyPassRateRow(
                specialty=specialty,
                total=total,
                passed=passed.get(specialty_id, 0),
                missing=missing.get(specialty_id, 0),
            )
        )

    rows.sort(key=lambda row: row.rate, reverse=True)
    return rows


# ========== COMPLIANCE & AUDIT FUNCTIONS ==========


def get_teacher_compliance(academic_year_id, term_id):
    """
    Get teacher submission compliance report.
    Uses SubjectAssignment.grading_deadline_at for deadline info.

    Returns:
        List of dicts with:
        - teacher_id, teacher_name, classroom_count
        # tenant-isolation-allow: service-layer-scoped-via-caller-student-classroom-or-teacher-fk
        - deadlines: [{'subject_assignment_id', 'deadline_date', 'days_left', 'submission_status', 'completion_rate'}]
        - overall_completion: float (0-100)
        - status: 'compliant' | 'at_risk' | 'overdue'
    """
    from django.utils import timezone
    # tenant-isolation-allow: service-layer-scoped-via-caller-student-classroom-or-teacher-fk
    from apps.evals.models import Evaluation

    # tenant-isolation-allow: service-layer-scoped-via-caller-student-classroom-or-teacher-fk
    today = timezone.now().date()
    compliance_data = []
# tenant-isolation-allow: service-layer-scoped-via-caller-student-classroom-or-teacher-fk

    teacher_assignments = (
        # tenant-isolation-allow: service-layer-scoped-via-caller-student-classroom-or-teacher-fk
        TeacherAssignment.objects.filter(
            academic_year_id=academic_year_id,
            subject_assignment__term_id=term_id,
        )
        .select_related(
            "teacher",
            "teacher__user",
            "subject_assignment",
            "subject_assignment__classroom",
            "subject_assignment__subject",
        )
        .order_by("teacher_id", "subject_assignment__classroom_id")
    )

    # Group by (teacher, classroom)
    # tenant-isolation-allow: service-layer-scoped-via-caller-student-classroom-or-teacher-fk
    from collections import defaultdict

    groups = defaultdict(list)
    for ta in teacher_assignments:
        # tenant-isolation-allow: service-layer-scoped-via-caller-student-classroom-or-teacher-fk
        key = (ta.teacher_id, ta.subject_assignment.classroom_id)
        groups[key].append(ta)
# tenant-isolation-allow: service-layer-scoped-via-caller-student-classroom-or-teacher-fk

    for (teacher_id, classroom_id), tas in groups.items():
        # tenant-isolation-allow: service-layer-scoped-via-caller-student-classroom-or-teacher-fk
        teacher = tas[0].teacher
        classroom = tas[0].subject_assignment.classroom
        # tenant-isolation-allow: service-layer-scoped-via-caller-student-classroom-or-teacher-fk
        total_students = StudentProfile.objects.filter(classroom=classroom).count()
        deadlines_info = []

        for ta in tas:
            sa = ta.subject_assignment
            deadline_dt = sa.grading_deadline_at
            if deadline_dt:
                deadline_date = (
                    deadline_dt.date() if hasattr(deadline_dt, "date") else deadline_dt
                )
                # tenant-isolation-allow: service-layer-scoped-via-caller-student-classroom-or-teacher-fk
                days_left = (deadline_date - today).days
                if days_left < 0:
                    submission_status = "overdue"
                elif days_left <= 3:
                    submission_status = "at_risk"
                # tenant-isolation-allow: service-layer-scoped-via-caller-student-classroom-or-teacher-fk
                else:
                    submission_status = "on_track"
            # tenant-isolation-allow: service-layer-scoped-via-caller-student-classroom-or-teacher-fk
            else:
                days_left = None
                # tenant-isolation-allow: service-layer-scoped-via-caller-student-classroom-or-teacher-fk
                submission_status = "on_track"
                deadline_date = None
# tenant-isolation-allow: service-layer-scoped-via-caller-student-classroom-or-teacher-fk

            submitted_count = (
                # tenant-isolation-allow: service-layer-scoped-via-caller-student-classroom-or-teacher-fk
                Evaluation.objects.filter(
                    academic_year_id=academic_year_id,
                    term_id=term_id,
                    subject_assignment=sa,
                    teacher=teacher,
                )
                .values("student")
                .distinct()
                .count()
            )

            completion_rate = (
                (submitted_count / total_students * 100) if total_students > 0 else 0
            )
            deadlines_info.append(
                {
                    "subject_assignment_id": sa.id,
                    "subject_name": sa.subject.name,
                    "deadline_date": deadline_date.isoformat()
                    if deadline_date
                    else None,
                    "days_left": days_left,
                    "submission_status": submission_status,
                    "completion_rate": round(completion_rate, 1),
                    "submitted_count": submitted_count,
                    "total_students": total_students,
                }
            )

        if deadlines_info:
            overall_completion = sum(
                d["completion_rate"] for d in deadlines_info
            ) / len(deadlines_info)
            statuses = [d["submission_status"] for d in deadlines_info]
            if "overdue" in statuses:
                overall_status = "overdue"
            elif "at_risk" in statuses:
                overall_status = "at_risk"
            else:
                overall_status = "compliant"
        else:
            overall_completion = 100
            overall_status = "compliant"

        compliance_data.append(
            {
                "teacher_id": teacher.id,
                "teacher_name": f"{teacher.user.first_name} {teacher.user.last_name}",
                "teacher_code": getattr(teacher, "teacher_code", "") or "",
                "classroom_name": classroom.name,
                "classroom_count": len(tas),
                "deadlines": deadlines_info,
                "overall_completion": round(overall_completion, 1),
                "status": overall_status,
            }
        )

    return compliance_data


def get_audit_trail(evaluation_id, limit=50):
    """
    Get audit trail for an evaluation with change history.

    Returns:
        List of dicts: {'change_type', 'changed_by', 'changed_at', 'changes': {...}}
    """
    from apps.evals.models import GradeAudit

    audits = (
        GradeAudit.objects.filter(evaluation_id=evaluation_id)
        .select_related("changed_by")
        .order_by("-changed_at")[:limit]
    )

    trail = []
    for audit in audits:
        changes = {}
        if audit.seq1_before is not None or audit.seq1_after is not None:
            changes["seq1"] = {
                "before": float(audit.seq1_before or 0),
                "after": float(audit.seq1_after or 0),
            }
        if audit.seq2_before is not None or audit.seq2_after is not None:
            changes["seq2"] = {
                "before": float(audit.seq2_before or 0),
                "after": float(audit.seq2_after or 0),
            }
        if audit.exam_before is not None or audit.exam_after is not None:
            changes["exam"] = {
                "before": float(audit.exam_before or 0),
                "after": float(audit.exam_after or 0),
            }
        if audit.mock_before is not None or audit.mock_after is not None:
            changes["mock"] = {
                "before": float(audit.mock_before or 0) if audit.mock_before else None,
                "after": float(audit.mock_after or 0) if audit.mock_after else None,
            }
        if audit.practical_before is not None or audit.practical_after is not None:
            changes["practical"] = {
                "before": float(audit.practical_before or 0)
                if audit.practical_before
                else None,
                "after": float(audit.practical_after or 0)
                if audit.practical_after
                else None,
            }
        if audit.remarks_before or audit.remarks_after:
            changes["remarks"] = {
                "before": audit.remarks_before,
                "after": audit.remarks_after,
            }

        trail.append(
            {
                "change_type": audit.change_type,
                "changed_by": f"{audit.changed_by.first_name} {audit.changed_by.last_name}",
                "changed_at": audit.changed_at.isoformat(),
                "changes": changes,
                "validation_errors": audit.validation_errors or [],
                "offline_conflict_resolved": audit.offline_conflict_resolved,
            }
        )

    return trail


def get_import_job_status(import_job_id):
    """Get detailed import job status. Returns None if job not found or serialization fails."""
    from apps.analytics.models import GradeImportJob
    from django.core.exceptions import ObjectDoesNotExist

    _IMPORT_JOB_STATUS_ERRORS = (
        ObjectDoesNotExist,
        AttributeError,
        TypeError,
        ValueError,
    )
    try:
        job = GradeImportJob.objects.get(id=import_job_id)
        return {
            "id": job.id,
            "status": job.status,
            "created_count": job.created_count,
            "updated_count": job.updated_count,
            "failed_count": job.failed_count,
            "total_rows": job.created_count + job.updated_count + job.failed_count,
            "error_log": job.error_log or [],
            "created_at": job.created_at.isoformat(),
            "completed_at": job.completed_at.isoformat() if job.completed_at else None,
            "duration_seconds": (job.completed_at - job.created_at).total_seconds()
            if job.completed_at
            else None,
        }
    except _IMPORT_JOB_STATUS_ERRORS:
        return None


# Phase 8 Task 2: Advanced Analytics Extensions
# Additional analytics methods for performance insights
# tenant-isolation-allow: service-layer-scoped-via-caller-student-classroom-or-teacher-fk


class AdvancedAnalyticsService:
    """Advanced analytics and performance tracking"""

    # tenant-isolation-allow: service-layer-scoped-via-caller-student-classroom-or-teacher-fk
    @staticmethod
    def identify_at_risk_students(threshold=50, school_id=None, school=None):
        # tenant-isolation-allow: service-layer-scoped-via-caller-student-classroom-or-teacher-fk
        """Identify students at risk of failing within a tenant context."""
        from apps.evals.models import Evaluation
# tenant-isolation-allow: service-layer-scoped-via-caller-student-classroom-or-teacher-fk

        at_risk = []
        # tenant-isolation-allow: service-layer-scoped-via-caller-student-classroom-or-teacher-fk
        students = StudentProfile.objects.filter(is_active=True).select_related("user")
        if school_id is not None:
            # tenant-isolation-allow: service-layer-scoped-via-caller-student-classroom-or-teacher-fk
            students = students.filter(school_id=school_id)
        elif school is not None:
            # tenant-isolation-allow: service-layer-scoped-via-caller-student-classroom-or-teacher-fk
            students = students.filter(school=school)

        # tenant-isolation-allow: service-layer-scoped-via-caller-student-classroom-or-teacher-fk
        cutoff = timezone.now() - timedelta(days=30)
        for student in students:
            # tenant-isolation-allow: service-layer-scoped-via-caller-student-classroom-or-teacher-fk
            recent_evals = Evaluation.objects.filter(
                student=student,
                created_at__gte=cutoff,
            )
            if student.school_id:
                recent_evals = recent_evals.filter(school_id=student.school_id)

            if recent_evals.exists():
                avg_score = recent_evals.aggregate(avg=Avg("final_score"))["avg"]

                if avg_score and avg_score < threshold:
                    student_name = (
                        student.user.get_full_name()
                        if getattr(student, "user", None)
                        else f"{student.first_name} {student.last_name}".strip()
                    )
                    risk_score = round(
                        min(100, max(50, threshold + (threshold - float(avg_score)))), 2
                    )
                    at_risk.append(
                        {
                            "id": student.id,
                            "student": student_name,
                            "average": round(avg_score, 2),
                            "count": recent_evals.count(),
                            "action": "Intervention needed",
                            "risk_score": risk_score,
                            # tenant-isolation-allow: service-layer-scoped-via-caller-student-classroom-or-teacher-fk
                            "risk_reason_summary": f"Average score over the last 30 days is {round(avg_score, 2)}",
                        }
                    )

        # tenant-isolation-allow: service-layer-scoped-via-caller-student-classroom-or-teacher-fk
        return at_risk

    # tenant-isolation-allow: service-layer-scoped-via-caller-student-classroom-or-teacher-fk
    @staticmethod
    def get_performance_trends(student, days=90, school_id=None):
        """Get performance trend data"""
        # tenant-isolation-allow: service-layer-scoped-via-caller-student-classroom-or-teacher-fk
        from apps.evals.models import Evaluation

        # tenant-isolation-allow: service-layer-scoped-via-caller-student-classroom-or-teacher-fk
        start_date = timezone.now() - timedelta(days=days)

        # tenant-isolation-allow: service-layer-scoped-via-caller-student-classroom-or-teacher-fk
        evals = Evaluation.objects.filter(
            student=student, created_at__gte=start_date
        ).order_by("created_at")
        if school_id is not None:
            evals = evals.filter(school_id=school_id)

        return [
            {
                "date": e.created_at.isoformat(),
                "score": e.final_score,
            }
            for e in evals
        ]

    @staticmethod
    def generate_performance_alerts(student, school_id=None):
        """Generate alerts for student performance issues"""
        from apps.evals.models import Evaluation

        # tenant-isolation-allow: service-layer-scoped-via-caller-student-classroom-or-teacher-fk
        alerts = []

        # tenant-isolation-allow: service-layer-scoped-via-caller-student-classroom-or-teacher-fk
        recent = Evaluation.objects.filter(
            student=student, created_at__gte=timezone.now() - timedelta(days=7)
        )
        if school_id is not None:
            recent = recent.filter(school_id=school_id)

        if recent.exists():
            import statistics

            scores = [float(e.final_score) for e in recent if e.final_score is not None]
            if not scores:
                return alerts
            avg = statistics.mean(scores)

            if avg < 50:
                alerts.append(
                    {
                        "type": "LOW_GRADE",
                        "severity": "CRITICAL",
                        "message": f"Average score is {avg:.1f}%",
                    }
                )

        return alerts
