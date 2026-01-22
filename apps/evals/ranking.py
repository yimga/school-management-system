"""
Enhanced ranking system with tie handling, caching, and performance optimization.

Phase 1.2: Complete Evaluation Module
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple

from django.core.cache import cache
from django.db.models import Q, Count, F, Max, Case, When, Value, CharField, FloatField
from django.db.models import Prefetch

from apps.academics.models import Term, Classroom, AcademicYear
from apps.people.models import StudentProfile

from .models import Evaluation


@dataclass(frozen=True)
class RankingEntry:
    """Entry in a ranking with position, ties, and metadata."""
    rank: int
    student: StudentProfile
    average: float
    tied_count: int = 1  # Number of students tied at this rank
    percentile: float = 0.0  # Percentile ranking (0-100)

    @property
    def is_tied(self) -> bool:
        """True if this student is tied with others."""
        return self.tied_count > 1


class RankingCache:
    """Cache strategy for rankings with proper invalidation."""

    @staticmethod
    def get_cache_key(term: Term, classroom: Optional[Classroom] = None) -> str:
        """Generate cache key for rankings."""
        if classroom:
            return f"ranking:term:{term.id}:class:{classroom.id}"
        return f"ranking:term:{term.id}:school"

    @staticmethod
    def get_rankings(
        term: Term,
        classroom: Optional[Classroom] = None,
        use_cache: bool = True,
    ) -> List[RankingEntry]:
        """
        Get rankings with caching and tie handling.

        Args:
            term: Academic term
            classroom: Optional classroom (if None, returns school-wide)
            use_cache: Whether to use cache (default True)

        Returns:
            List of RankingEntry objects sorted by rank
        """
        cache_key = RankingCache.get_cache_key(term, classroom)

        if use_cache:
            cached = cache.get(cache_key)
            if cached is not None:
                return cached

        # Compute fresh rankings
        rankings = _compute_rankings(term, classroom)

        # Cache for 15 minutes
        cache.set(cache_key, rankings, 900)

        return rankings

    @staticmethod
    def invalidate(term: Term, classroom: Optional[Classroom] = None):
        """Invalidate ranking cache for a term/classroom."""
        cache_key = RankingCache.get_cache_key(term, classroom)
        cache.delete(cache_key)

        # Also invalidate school-wide if invalidating a class
        if classroom:
            school_key = RankingCache.get_cache_key(term, None)
            cache.delete(school_key)


def _compute_rankings(
    term: Term,
    classroom: Optional[Classroom] = None,
) -> List[RankingEntry]:
    """
    Compute rankings with proper tie handling and optimized queries.

    Optimization:
    - Single batch query for all evaluations
    - Batch process in Python
    - Proper tie detection
    - Percentile calculation
    """

    # Get students to rank
    if classroom:
        students = StudentProfile.objects.filter(
            classroom=classroom,
            is_active=True,
        ).select_related("classroom")
    else:
        students = StudentProfile.objects.filter(
            is_active=True,
        ).select_related("classroom")

    # Batch-load all evaluations for this term
    evaluations = Evaluation.objects.filter(
        term=term,
        student__in=students,
    ).select_related(
        "student",
        "subject_assignment__subject",
        "subject_assignment__classroom",
    )

    # Compute averages efficiently
    student_averages: dict[int, float] = {}

    for eval_obj in evaluations:
        student_id = eval_obj.student_id
        if student_id not in student_averages:
            # Compute average for this student
            student_evals = evaluations.filter(student_id=student_id)
            avg = _compute_student_average(student_evals)
            student_averages[student_id] = avg

    # Create aggregates: (student, average) tuples
    aggregates = []
    for student in students:
        avg = student_averages.get(student.id, 0.0)
        if avg is not None:
            aggregates.append((student, avg))

    # Sort by average (descending), then by name, then by ID for stability
    aggregates.sort(
        key=lambda x: (-x[1], x[0].last_name, x[0].first_name, x[0].id)
    )

    # Build ranking entries with tie handling
    rankings = []
    current_rank = 1
    prev_average = None

    for idx, (student, average) in enumerate(aggregates):
        # Check for tie with previous student
        if prev_average is not None and abs(average - prev_average) < 0.001:
            # Tied with previous student
            rank = rankings[-1].rank
        else:
            # New rank
            rank = idx + 1
            current_rank = rank

        # Count how many students are tied at this rank
        tied_count = 1
        if idx + 1 < len(aggregates):
            next_avg = aggregates[idx + 1][1]
            tied_count = sum(
                1 for _, a in aggregates[idx:]
                if abs(a - average) < 0.001
            )

        # Calculate percentile (0-100)
        percentile = 100.0 - ((current_rank - 1) / max(len(aggregates), 1)) * 100.0

        entry = RankingEntry(
            rank=rank,
            student=student,
            average=round(average, 2),
            tied_count=tied_count,
            percentile=round(percentile, 2),
        )
        rankings.append(entry)
        prev_average = average

    return rankings


def _compute_student_average(evaluations) -> float:
    """
    Compute weighted average for a student from evaluations queryset.

    Uses subject coefficient for weighting:
    Average = sum(score * coefficient) / sum(coefficients)
    """
    total_weighted = 0.0
    total_coef = 0.0

    for eval_obj in evaluations:
        if not eval_obj.total_score:
            continue

        coef = float(eval_obj.subject_assignment.coefficient or 1.0)
        score = float(eval_obj.total_score)

        total_weighted += score * coef
        total_coef += coef

    if total_coef <= 0:
        return 0.0

    return total_weighted / total_coef


def get_class_ranking(
    classroom: Classroom,
    term: Term,
) -> List[RankingEntry]:
    """Get class ranking with caching and tie handling."""
    return RankingCache.get_rankings(term, classroom)


def get_school_ranking(term: Term) -> List[RankingEntry]:
    """Get school-wide ranking with caching and tie handling."""
    return RankingCache.get_rankings(term, None)


def get_student_rank(
    student: StudentProfile,
    term: Term,
    classroom: Optional[Classroom] = None,
) -> Optional[int]:
    """
    Get a specific student's rank in the rankings.

    Returns:
        Rank number or None if student not found
    """
    rankings = RankingCache.get_rankings(term, classroom or student.classroom)
    for entry in rankings:
        if entry.student_id == student.id:
            return entry.rank
    return None


def get_rank_position_with_context(
    student: StudentProfile,
    term: Term,
) -> dict:
    """
    Get full ranking context for a student.

    Returns:
        {
            'class_rank': int or None,
            'class_size': int,
            'school_rank': int or None,
            'school_size': int,
            'class_percentile': float,
            'school_percentile': float,
            'is_tied': bool,
            'average': float,
        }
    """
    # Get class ranking
    class_rankings = get_class_ranking(student.classroom, term) if student.classroom else []
    class_rank = None
    class_percentile = 0.0
    is_tied_class = False

    for entry in class_rankings:
        if entry.student_id == student.id:
            class_rank = entry.rank
            class_percentile = entry.percentile
            is_tied_class = entry.is_tied
            break

    # Get school ranking
    school_rankings = get_school_ranking(term)
    school_rank = None
    school_percentile = 0.0
    is_tied_school = False
    student_average = 0.0

    for entry in school_rankings:
        if entry.student_id == student.id:
            school_rank = entry.rank
            school_percentile = entry.percentile
            is_tied_school = entry.is_tied
            student_average = entry.average
            break

    return {
        'class_rank': class_rank,
        'class_size': len(class_rankings),
        'school_rank': school_rank,
        'school_size': len(school_rankings),
        'class_percentile': class_percentile,
        'school_percentile': school_percentile,
        'is_tied': is_tied_class or is_tied_school,
        'average': student_average,
    }
