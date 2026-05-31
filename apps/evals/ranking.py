"""
Enhanced ranking system with tie handling, caching, and performance optimization.

Phase 1.2: Complete Evaluation Module
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass
from typing import List, Optional

from django.core.cache import cache

from apps.academics.models import Term, Classroom
from apps.siteconfig.cache_utils import get_tenant_cache_prefix
from apps.people.models import StudentProfile

from .models import Evaluation, MockExamSetting
from .mock_exams import calculate_blended_score


@dataclass(frozen=True)
class RankingEntry:
    """Entry in a ranking with position, ties, and metadata."""

    rank: int
    student: StudentProfile
    student_id: int
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
    def get_cache_key(
        term: Term,
        classroom: Optional[Classroom] = None,
        use_mock_blending: bool = False,
    ) -> str:
        """Generate cache key for rankings (tenant-scoped to avoid cross-tenant leakage)."""
        school_id = getattr(classroom, "school_id", None) or getattr(
            term, "school_id", None
        )
        prefix = f"school:{school_id}" if school_id else get_tenant_cache_prefix()
        mock_suffix = ":mock" if use_mock_blending else ""
        if classroom:
            return f"{prefix}:ranking:term:{term.id}:class:{classroom.id}{mock_suffix}"
        return f"{prefix}:ranking:term:{term.id}:school{mock_suffix}"

    @staticmethod
    def get_rankings(
        term: Term,
        classroom: Optional[Classroom] = None,
        use_cache: bool = True,
        use_mock_blending: bool = False,
    ) -> List[RankingEntry]:
        """
        Get rankings with caching and tie handling.

        Args:
            term: Academic term
            classroom: Optional classroom (if None, returns school-wide)
            use_cache: Whether to use cache (default True)
            use_mock_blending: Whether to blend mock exam scores for FORM 5/7 (default False)

        Returns:
            List of RankingEntry objects sorted by rank
        """
        cache_key = RankingCache.get_cache_key(term, classroom, use_mock_blending)

        if use_cache:
            cached = cache.get(cache_key)
            if cached is not None:
                return cached

        # Compute fresh rankings
        rankings = _compute_rankings(term, classroom, use_mock_blending)

        # Cache for 15 minutes
        cache.set(cache_key, rankings, 900)

        return rankings

    @staticmethod
    def invalidate(term: Term, classroom: Optional[Classroom] = None):
        """Invalidate ranking cache for a term/classroom (both regular and mock-blended)."""
        # Invalidate both regular and mock-blended versions
        for use_mock in [False, True]:
            cache_key = RankingCache.get_cache_key(term, classroom, use_mock)
            cache.delete(cache_key)

        # Also invalidate school-wide if invalidating a class
        if classroom:
            for use_mock in [False, True]:
                school_key = RankingCache.get_cache_key(term, None, use_mock)
                cache.delete(school_key)


def _compute_rankings(
    term: Term,
    classroom: Optional[Classroom] = None,
    use_mock_blending: bool = False,
) -> List[RankingEntry]:
    """
    Compute rankings with proper tie handling and optimized queries.

    Args:
        term: Academic term
        classroom: Optional classroom (if None, returns school-wide)
        use_mock_blending: Whether to apply mock exam blending (for FORM 5/7)

    Optimization:
    - Single batch query for all evaluations
    - Batch process in Python
    - Proper tie detection
    - Percentile calculation
    """

    # Get students to rank
    if classroom:
        # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
        students = StudentProfile.objects.filter(
            classroom=classroom,
            is_active=True,
        ).select_related("classroom")
    # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
    else:
        students = StudentProfile.objects.filter(
            is_active=True,
        ).select_related("classroom")

    # Get mock exam setting if blending enabled
    mock_setting = None
    if use_mock_blending and classroom:
        mock_setting = MockExamSetting.get_for(term.academic_year, classroom, term)

    # Batch-load all evaluations for this term (once)
    # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
    evaluations_qs = Evaluation.objects.filter(
        term=term,
        student__in=students,
    ).select_related(
        "student",
        "subject_assignment__subject",
        "subject_assignment__classroom",
    )

    evaluations = list(evaluations_qs)
    student_evals_map: dict[int, list[Evaluation]] = {}

    for eval_obj in evaluations:
        student_evals_map.setdefault(eval_obj.student_id, []).append(eval_obj)

    student_averages: dict[int, float] = {}
    for student_id, eval_list in student_evals_map.items():
        avg = _compute_student_average(
            eval_list,
            use_mock_blending=use_mock_blending,
            mock_setting=mock_setting,
        )
        student_averages[student_id] = avg

    # Create aggregates: (student, average) tuples
    aggregates = []
    for student in students:
        avg = student_averages.get(student.id, 0.0)
        if avg is not None:
            aggregates.append((student, avg))

    ranking_mode = _resolve_ranking_mode(term, classroom)
    if ranking_mode == "standard_score_t" and len(aggregates) > 1:
        scores = [avg for _, avg in aggregates]
        mean = statistics.mean(scores)
        stdev = statistics.pstdev(scores) or 1.0
        aggregates = [
            (
                student,
                round(50.0 + 10.0 * ((avg - mean) / stdev), 2),
            )
            for student, avg in aggregates
        ]

    # Sort by average (descending), then by name, then by ID for stability
    aggregates.sort(key=lambda x: (-x[1], x[0].last_name, x[0].first_name, x[0].id))

    rankings = []
    idx = 0
    current_rank = 1
    group_eps = 0.001
    total_students = len(aggregates)

    while idx < total_students:
        student, average = aggregates[idx]
        group_end = idx + 1
        while (
            group_end < total_students
            and abs(aggregates[group_end][1] - average) < group_eps
        ):
            group_end += 1

        group_size = group_end - idx
        percentile = 100.0 - ((current_rank - 1) / max(total_students, 1)) * 100.0

        for j in range(idx, group_end):
            student_j, avg_j = aggregates[j]
            entry = RankingEntry(
                rank=current_rank,
                student=student_j,
                student_id=student_j.id,
                average=round(avg_j, 2),
                tied_count=group_size,
                percentile=round(percentile, 2),
            )
            rankings.append(entry)

        current_rank += group_size
        idx = group_end

    return rankings


def _compute_student_average(
    evaluations,
    use_mock_blending: bool = False,
    mock_setting: Optional[MockExamSetting] = None,
) -> float:
    """
    Compute weighted average for a student from evaluations queryset.

    With mock blending: replaces exam_score with blended (final × 0.7 + mock × 0.3).

    Args:
        evaluations: Queryset of Evaluation objects
        use_mock_blending: Whether to blend mock exam scores
        mock_setting: MockExamSetting for blending weights (required if use_mock_blending=True)

    Uses subject coefficient for weighting:
    Average = sum(score * coefficient) / sum(coefficients)
    """
    total_weighted = 0.0
    total_coef = 0.0

    for eval_obj in evaluations:
        if not eval_obj.total_score:
            continue

        coef = float(eval_obj.subject_assignment.coefficient or 1.0)

        # Calculate score: use blended if mock exam enabled
        if use_mock_blending and mock_setting and eval_obj.exam_score is not None:
            score = float(
                calculate_blended_score(
                    eval_obj.exam_score, eval_obj.mock_score, mock_setting
                )
            )
        else:
            score = float(eval_obj.total_score)

        total_weighted += score * coef
        total_coef += coef

    if total_coef <= 0:
        return 0.0

    return total_weighted / total_coef


def _resolve_ranking_mode(term: Term, classroom: Optional[Classroom]) -> str:
    school = getattr(classroom, "school", None) or getattr(term, "school", None)
    if school is None:
        return "average"
    try:
        from apps.policies.resolver import get_effective_policy
        from apps.registries.grade_scale_resolver import resolve_grade_scale_for_tenant

        policy = get_effective_policy(school)
        preset = (policy.get("grading") or {}).get("preset_key")
        if preset == "east_asia_competitive":
            return "standard_score_t"
        scale = resolve_grade_scale_for_tenant(school)
        if scale and isinstance(scale.metadata, dict):
            return str(scale.metadata.get("ranking_mode") or "average")
    except (ImportError, AttributeError, TypeError, ValueError):
        pass
    return "average"


def get_class_ranking(
    classroom: Classroom,
    term: Term,
    use_mock_blending: bool = False,
    use_cache: bool = True,
) -> List[RankingEntry]:
    """
    Get class ranking with caching and tie handling.

    Args:
        classroom: Classroom to rank
        term: Academic term
        use_mock_blending: Whether to blend mock exam scores

    Returns:
        List of ranking entries with positions and percentiles
    """
    return RankingCache.get_rankings(
        term,
        classroom,
        use_mock_blending=use_mock_blending,
        use_cache=use_cache,
    )


def get_school_ranking(
    term: Term,
    use_mock_blending: bool = False,
    use_cache: bool = True,
) -> List[RankingEntry]:
    """
    Get school-wide ranking with caching and tie handling.

    Args:
        term: Academic term
        use_mock_blending: Whether to blend mock exam scores

    Returns:
        List of ranking entries with positions and percentiles
    """
    return RankingCache.get_rankings(
        term,
        None,
        use_mock_blending=use_mock_blending,
        use_cache=use_cache,
    )


def get_student_rank(
    student: StudentProfile,
    term: Term,
    classroom: Optional[Classroom] = None,
    use_mock_blending: bool = False,
) -> Optional[int]:
    """
    Get a specific student's rank in the rankings.

    Args:
        student: Student to find rank for
        term: Academic term
        classroom: Specific classroom (defaults to student's classroom)
        use_mock_blending: Whether to blend mock exam scores

    Returns:
        Rank number or None if student not found
    """
    rankings = RankingCache.get_rankings(
        term, classroom or student.classroom, use_mock_blending=use_mock_blending
    )
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
    class_rankings = (
        get_class_ranking(student.classroom, term) if student.classroom else []
    )
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
        "class_rank": class_rank,
        "class_size": len(class_rankings),
        "school_rank": school_rank,
        "school_size": len(school_rankings),
        "class_percentile": class_percentile,
        "school_percentile": school_percentile,
        "is_tied": is_tied_class or is_tied_school,
        "average": student_average,
    }
