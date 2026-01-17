"""Evaluation computations (rankings, averages).

Keep business logic out of views/templates so it remains testable and reusable.

This is intentionally *simple* for Release 1:
- Term average = mean of Evaluation.total_score across evaluations in that term.
- Rankings = sort by term average desc.

Later releases can replace the math with Cameroon-style components:
seq1/seq2/exam/mock/practical + weights per school/class.
"""

from __future__ import annotations

from dataclasses import dataclass
from statistics import mean, median
from typing import Iterable, List, Optional, Sequence

from django.db.models import QuerySet

from apps.academics.models import Term, ClassRoom
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
    return Evaluation.objects.filter(term=term).select_related("student", "subject", "term")


def student_term_scores(student: StudentProfile, term: Term) -> List[float]:
    qs = Evaluation.objects.filter(student=student, term=term)
    return [float(e.total_score) for e in qs]


def student_term_average(student: StudentProfile, term: Term) -> float:
    scores = student_term_scores(student, term)
    return float(mean(scores)) if scores else 0.0


def classroom_term_rankings(classroom: ClassRoom, term: Term) -> List[StudentAggregate]:
    students = StudentProfile.objects.filter(classroom=classroom, is_active=True).select_related("classroom")
    aggregates: List[StudentAggregate] = []

    for s in students:
        scores = student_term_scores(s, term)
        aggregates.append(StudentAggregate(student=s, term=term, scores=scores))

    # Highest average first
    aggregates.sort(key=lambda a: a.average, reverse=True)
    return aggregates


def school_term_rankings(term: Term) -> List[StudentAggregate]:
    students = StudentProfile.objects.filter(is_active=True).select_related("classroom")
    aggregates: List[StudentAggregate] = []
    for s in students:
        scores = student_term_scores(s, term)
        aggregates.append(StudentAggregate(student=s, term=term, scores=scores))

    aggregates.sort(key=lambda a: a.average, reverse=True)
    return aggregates


def classroom_stats(classroom: ClassRoom, term: Term) -> dict:
    """Mean/median for the class (based on students' term averages)."""
    ranks = classroom_term_rankings(classroom, term)
    avgs = [r.average for r in ranks]
    return {
        "mean": float(mean(avgs)) if avgs else 0.0,
        "median": float(median(avgs)) if avgs else 0.0,
        "count": len(avgs),
    }
