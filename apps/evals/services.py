"""Evaluation computations (rankings, averages).

Keep business logic out of views/templates so it remains testable and reusable.

Release 1 goal:
- Expand evaluation components (seq1/seq2/exam/mock/practical)
- Use configurable weights (school-wide + per classroom)
- Compute *coefficient-weighted* term averages
- Produce rankings + class stats
"""

from __future__ import annotations

from dataclasses import dataclass
from statistics import mean, median
from typing import Iterable, List, Optional, Sequence

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
        # Term average already computed with subject coefficients; here we expose
        # it for sorting/UI.
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
    """Return per-subject final scores (already weighted by AssessmentWeights)."""
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
    """Coefficient-weighted term average for a student.

    average = sum(subject_score * coefficient) / sum(coefficients)
    """
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

    # Highest average first
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
    """Mean/median for the class (based on students' term averages)."""
    ranks = classroom_term_rankings(classroom, term)
    avgs = [r.average for r in ranks]
    return {
        "mean": float(mean(avgs)) if avgs else 0.0,
        "median": float(median(avgs)) if avgs else 0.0,
        "count": len(avgs),
    }
