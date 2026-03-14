"""Evaluation computations (rankings, averages, completion).

Keep business logic out of views/templates so it remains testable and reusable.
"""

from __future__ import annotations

from dataclasses import dataclass
from statistics import mean, median
from typing import List, Optional

from django.db.models import QuerySet

from apps.academics.models import Term, Classroom
from apps.people.models import StudentProfile

from .models import Evaluation


@dataclass(frozen=True)
class StudentAggregate:
    student: StudentProfile
    term: Term
    scores: List[float]

    @property
    def average(self) -> float:
        return float(mean(self.scores)) if self.scores else 0.0


def evaluations_for_term(term: Term) -> QuerySet[Evaluation]:
    return Evaluation.objects.filter(term=term).select_related(
        "student",
        "term",
        "academic_year",
        "subject_assignment",
        "subject_assignment__subject",
        "subject_assignment__classroom",
    )


def student_term_subject_scores(student: StudentProfile, term: Term) -> List[float]:
    qs = (
        Evaluation.objects.filter(student=student, term=term)
        .select_related(
            "academic_year",
            "term",
            "subject_assignment",
            "subject_assignment__subject",
            "subject_assignment__classroom",
        )
    )
    return [float(e.total_score) for e in qs]


def student_term_average(student: StudentProfile, term: Term) -> float:
    evals = (
        Evaluation.objects.filter(student=student, term=term)
        .select_related("subject_assignment")
    )

    total_weighted = 0.0
    total_coef = 0.0
    for e in evals:
        coef = float(e.subject_assignment.coefficient or 1)
        score = float(e.total_score)
        total_weighted += score * coef
        total_coef += coef

    return (total_weighted / total_coef) if total_coef else 0.0


def classroom_term_rankings(classroom: Classroom, term: Term) -> List[StudentAggregate]:
    students = StudentProfile.objects.filter(classroom=classroom, is_active=True).select_related("classroom")
    aggregates: List[StudentAggregate] = []

    for s in students:
        aggregates.append(StudentAggregate(student=s, term=term, scores=[student_term_average(s, term)]))

    aggregates.sort(key=lambda a: a.average, reverse=True)
    return aggregates


def school_term_rankings(term: Term) -> List[StudentAggregate]:
    students = StudentProfile.objects.filter(is_active=True).select_related("classroom")
    aggregates: List[StudentAggregate] = []
    for s in students:
        aggregates.append(StudentAggregate(student=s, term=term, scores=[student_term_average(s, term)]))

    aggregates.sort(key=lambda a: a.average, reverse=True)
    return aggregates


def classroom_stats(classroom: Classroom, term: Term) -> dict:
    ranks = classroom_term_rankings(classroom, term)
    avgs = [r.average for r in ranks]
    return {
        "mean": float(mean(avgs)) if avgs else 0.0,
        "median": float(median(avgs)) if avgs else 0.0,
        "count": len(avgs),
    }


def get_class_ranking(classroom: Classroom, year: Optional[object], term: Term) -> List[StudentAggregate]:
    return classroom_term_rankings(classroom, term)


def get_school_ranking(year: Optional[object], term: Term) -> List[StudentAggregate]:
    return school_term_rankings(term)


def get_class_stats(classroom: Classroom, year: Optional[object], term: Term) -> dict:
    return classroom_stats(classroom, term)


@dataclass
class CompletionStats:
    total: int
    completed: int
    pending: int
    completion_pct: float


def completion_for_assignment(subject_assignment, term) -> CompletionStats:
    """
    Return completion stats for a subject assignment/term pair.
    Completed = evaluations with at least one score filled.
    """
    classroom = getattr(subject_assignment, "classroom", None)
    total_students = classroom.students.count() if classroom else 0

    eval_qs = Evaluation.objects.filter(
        subject_assignment=subject_assignment,
        term=term,
    )
    completed = eval_qs.exclude(
        seq1_score__isnull=True,
        seq2_score__isnull=True,
        exam_score__isnull=True,
        mock_score__isnull=True,
        practical_score__isnull=True,
        test1__isnull=True,
        test2__isnull=True,
    ).count()

    pending = max(total_students - completed, 0)
    pct = 0.0
    if total_students > 0:
        pct = round((completed / total_students) * 100, 2)

    return CompletionStats(
        total=total_students,
        completed=completed,
        pending=pending,
        completion_pct=pct,
    )


def ews_students_needing_attention(teacher_profile, year, term, assignments, scale: float = 20.0, drop_threshold_pct: float = 10.0):
    """
    Early warning: students with grade drop > threshold (e.g. 10% of scale) vs previous term.
    Returns list of dicts: {student_name, subject, classroom, drop_points}.
    """
    if not teacher_profile or not year or not term or not assignments:
        return []
    prev_term = (
        Term.objects.filter(academic_year=year, position=term.position - 1)
        .order_by("position")
        .first()
    )
    if not prev_term:
        return []
    from apps.academics.models import SubjectAssignment

    drop_min = scale * (drop_threshold_pct / 100.0)  # e.g. 2 on 20 scale for 10%
    result = []
    seen = set()  # (student_id, subject_id) to avoid duplicates

    for ta in assignments:
        sa = getattr(ta, "subject_assignment", None)
        if not sa or not getattr(sa, "classroom", None) or not getattr(sa, "subject", None):
            continue
        prev_sa = (
            SubjectAssignment.objects.filter(
                academic_year=year,
                term=prev_term,
                classroom=sa.classroom,
                subject=sa.subject,
            )
            .first()
        )
        if not prev_sa:
            continue
        curr_evals = {
            e.student_id: (e.final_score or e.total_score)
            for e in Evaluation.objects.filter(
                subject_assignment=sa, term=term
            ).select_related("student")
        }
        prev_evals = {
            e.student_id: (e.final_score or e.total_score)
            for e in Evaluation.objects.filter(
                subject_assignment=prev_sa, term=prev_term
            )
        }
        for sid, curr_val in curr_evals.items():
            if sid not in prev_evals:
                continue
            prev_val = prev_evals[sid]
            if prev_val is None or curr_val is None:
                continue
            try:
                prev_f = float(prev_val)
                curr_f = float(curr_val)
            except (TypeError, ValueError):
                continue
            drop = prev_f - curr_f
            if drop < drop_min:
                continue
            key = (sid, sa.subject_id)
            if key in seen:
                continue
            seen.add(key)
            ev = Evaluation.objects.filter(subject_assignment=sa, term=term, student_id=sid).select_related("student").first()
            student_name = ev.student.get_full_name() if ev and ev.student else f"Student {sid}"
            result.append({
                "student_name": student_name,
                "subject": sa.subject.name,
                "classroom": sa.classroom.name,
                "drop_points": round(drop, 1),
            })
    return result[:20]  # cap for dashboard
