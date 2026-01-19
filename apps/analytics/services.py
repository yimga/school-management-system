from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time
from decimal import Decimal
from typing import Iterable, Optional

from django.utils import timezone

from apps.academics.models import AcademicYear, Term, Classroom, Specialty, Subject
from apps.evals.models import AssessmentWeights, Evaluation, TeacherAssignment
from apps.people.models import StudentProfile, TeacherProfile
from apps.reports.models import PromotionRule, TermPublishStatus

from .models import GradingDeadline

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
    qs = GradingDeadline.objects.filter(academic_year=academic_year, term=term)
    if classroom:
        obj = qs.filter(classroom=classroom).first()
        if obj:
            return obj.deadline_at
    obj = qs.filter(classroom__isnull=True).first()
    return obj.deadline_at if obj else None


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


def required_fields(academic_year: AcademicYear, classroom: Optional[Classroom], term: Term) -> list[str]:
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


def term_rankings(term: Term, classroom: Optional[Classroom] = None) -> list[tuple[StudentProfile, float]]:
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
    terms: Iterable[Term],
    classroom: Optional[Classroom] = None,
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
    academic_year: AcademicYear,
    term: Term,
    deadline_mode: str,
) -> list[TeacherComplianceRow]:
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
        stats.setdefault(teacher.id, {"expected": 0, "on_time": 0, "late": 0, "missing": 0})

        sa = assignment.subject_assignment
        classroom = sa.classroom
        deadline_at = resolve_deadline(academic_year, term, classroom, deadline_mode)
        fields = required_fields(academic_year, classroom, term)

        students = StudentProfile.objects.filter(
            academic_year=academic_year,
            classroom=classroom,
            specialty=sa.specialty,
            is_active=True,
        )
        expected = students.count()

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


def subject_weaknesses(
    academic_year: AcademicYear,
    term: Term,
    classroom: Optional[Classroom],
    specialty: Optional[Specialty],
    threshold: Decimal,
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
            rows.append(SubjectAverageRow(subject=subjects[subject_id], average=avg, count=count))

    rows.sort(key=lambda row: row.average)
    return rows


def student_improvements(
    academic_year: AcademicYear,
    from_term: Term,
    to_term: Term,
    classroom: Optional[Classroom],
    min_delta: Decimal,
) -> list[StudentImprovementRow]:
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
    academic_year: AcademicYear,
    term: Optional[Term],
    pass_mark: Decimal,
    use_promotion_rule: bool,
) -> list[SpecialtyPassRateRow]:
    terms = [term] if term else list(Term.objects.filter(academic_year=academic_year).order_by("start_date"))
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
        avg = annual_average(student, terms) if term is None else term_average(student, term)
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
