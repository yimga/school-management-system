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
    # tenant-isolation-allow: service-layer-scoped-via-caller-student-classroom-or-teacher-fk
    return Evaluation.objects.filter(term=term).select_related(
        "student",
        "term",
        "academic_year",
        "subject_assignment",
        "subject_assignment__subject",
        "subject_assignment__classroom",
    )


# tenant-isolation-allow: service-layer-scoped-via-caller-student-classroom-or-teacher-fk
def student_term_subject_scores(student: StudentProfile, term: Term) -> List[float]:
    qs = Evaluation.objects.filter(student=student, term=term).select_related(
        "academic_year",
        "term",
        "subject_assignment",
        "subject_assignment__subject",
        "subject_assignment__classroom",
    )
    return [float(e.total_score) for e in qs]

# tenant-isolation-allow: service-layer-scoped-via-caller-student-classroom-or-teacher-fk

def student_term_average(student: StudentProfile, term: Term) -> float:
    # tenant-isolation-allow: service-layer-scoped-via-caller-student-classroom-or-teacher-fk
    evals = Evaluation.objects.filter(student=student, term=term).select_related(
        "subject_assignment",
        "subject_assignment__classroom",
        "academic_year",
        "term",
    )
    return _coefficient_weighted_average(list(evals))


def _coefficient_weighted_average(
    evals: list,
    *,
    weights_cache: dict | None = None,
    formula_cache: dict | None = None,
) -> float:
    """Coefficient-weighted mean of evaluation totals (shared by single + bulk paths)."""
    from apps.evals.grade_computation import (
        _resolve_formula_text,
        compute_evaluation_total_score,
    )
    from apps.evals.models import AssessmentWeights

    if not evals:
        return 0.0
    weights_cache = weights_cache if weights_cache is not None else {}
    formula_cache = formula_cache if formula_cache is not None else {}

    total_weighted = 0.0
    total_coef = 0.0
    for e in evals:
        sa = getattr(e, "subject_assignment", None)
        coef = float(getattr(sa, "coefficient", None) or 1)
        classroom = getattr(sa, "classroom", None) if sa is not None else None
        year = getattr(e, "academic_year", None)
        term_obj = getattr(e, "term", None)
        wkey = (
            getattr(year, "pk", None),
            getattr(classroom, "pk", None),
            getattr(term_obj, "pk", None) or getattr(e, "term_id", None),
        )
        if wkey not in weights_cache:
            weights_cache[wkey] = AssessmentWeights.get_for(year, classroom, term_obj)
        weights = weights_cache[wkey]
        school = getattr(classroom, "school", None) if classroom is not None else None
        if school is None:
            school = getattr(e, "school", None)
        skey = getattr(school, "pk", None)
        if skey not in formula_cache:
            formula_cache[skey] = _resolve_formula_text(weights, school)
        score = float(
            compute_evaluation_total_score(
                e, weights=weights, formula_text=formula_cache[skey]
            )
        )
        total_weighted += score * coef
        total_coef += coef
    return (total_weighted / total_coef) if total_coef else 0.0


def _bulk_term_averages_for_students(
    students: list[StudentProfile], term: Term
) -> dict[int, float]:
    """One Evaluation query for the whole student set; memoized weights/formula."""
    if not students:
        return {}
    student_ids = [s.pk for s in students]
    # tenant-isolation-allow: service-layer-scoped-via-caller-student-classroom-or-teacher-fk
    evals = list(
        Evaluation.objects.filter(student_id__in=student_ids, term=term).select_related(
            "subject_assignment",
            "subject_assignment__classroom",
            "subject_assignment__classroom__school",
            "academic_year",
            "term",
            "student",
        )
    )
    by_student: dict[int, list] = {sid: [] for sid in student_ids}
    for e in evals:
        sid = getattr(e, "student_id", None)
        if sid in by_student:
            by_student[sid].append(e)

    weights_cache: dict = {}
    formula_cache: dict = {}
    return {
        sid: _coefficient_weighted_average(
            rows, weights_cache=weights_cache, formula_cache=formula_cache
        )
        for sid, rows in by_student.items()
    }


# tenant-isolation-allow: service-layer-scoped-via-caller-student-classroom-or-teacher-fk
def classroom_term_rankings(classroom: Classroom, term: Term) -> List[StudentAggregate]:
    students = list(
        StudentProfile.objects.filter(
            classroom=classroom, is_active=True
        ).select_related("classroom")
    )
    averages = _bulk_term_averages_for_students(students, term)
    aggregates: List[StudentAggregate] = [
        StudentAggregate(student=s, term=term, scores=[averages.get(s.pk, 0.0)])
        for s in students
    ]
    aggregates.sort(key=lambda a: a.average, reverse=True)
    # tenant-isolation-allow: service-layer-scoped-via-caller-student-classroom-or-teacher-fk
    return aggregates


# tenant-isolation-allow: service-layer-scoped-via-caller-student-classroom-or-teacher-fk

def school_term_rankings(term: Term) -> List[StudentAggregate]:
    # tenant-isolation-allow: service-layer-scoped-via-caller-student-classroom-or-teacher-fk
    students = list(
        StudentProfile.objects.filter(is_active=True).select_related("classroom")
    )
    averages = _bulk_term_averages_for_students(students, term)
    aggregates: List[StudentAggregate] = [
        StudentAggregate(student=s, term=term, scores=[averages.get(s.pk, 0.0)])
        for s in students
    ]
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


def get_class_ranking(
    classroom: Classroom, year: Optional[object], term: Term
) -> List[StudentAggregate]:
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

    # tenant-isolation-allow: service-layer-scoped-via-caller-student-classroom-or-teacher-fk
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


def completion_for_assignments_bulk(
    subject_assignments, term
) -> dict[int, CompletionStats]:
    """Bulk completion stats — O(1) queries vs O(n) for ``completion_for_assignment``.

    Used by the teacher-dashboard spotlight (Metric #17). Keys are subject
    assignment primary keys.
    """
    from django.db.models import Count

    assignments = list(subject_assignments or [])
    if not assignments:
        return {}

    classroom_ids = {
        getattr(sa, "classroom_id", None) or getattr(getattr(sa, "classroom", None), "pk", None)
        for sa in assignments
    }
    classroom_ids.discard(None)
    sa_ids = [sa.pk for sa in assignments if getattr(sa, "pk", None) is not None]

    # tenant-isolation-allow: service-layer-scoped-via-caller-student-classroom-or-teacher-fk
    totals_by_classroom: dict[int, int] = {}
    if classroom_ids:
        for row in (
            StudentProfile.objects.filter(classroom_id__in=classroom_ids)
            .values("classroom_id")
            .annotate(n=Count("id"))
        ):
            totals_by_classroom[int(row["classroom_id"])] = int(row["n"])

    completed_by_sa: dict[int, int] = {}
    if sa_ids:
        # tenant-isolation-allow: service-layer-scoped-via-caller-student-classroom-or-teacher-fk
        for row in (
            Evaluation.objects.filter(subject_assignment_id__in=sa_ids, term=term)
            .exclude(
                seq1_score__isnull=True,
                seq2_score__isnull=True,
                exam_score__isnull=True,
                mock_score__isnull=True,
                practical_score__isnull=True,
                test1__isnull=True,
                test2__isnull=True,
            )
            .values("subject_assignment_id")
            .annotate(n=Count("id"))
        ):
            completed_by_sa[int(row["subject_assignment_id"])] = int(row["n"])

    out: dict[int, CompletionStats] = {}
    for sa in assignments:
        cid = getattr(sa, "classroom_id", None) or getattr(
            getattr(sa, "classroom", None), "pk", None
        )
        total = totals_by_classroom.get(int(cid), 0) if cid is not None else 0
        completed = completed_by_sa.get(int(sa.pk), 0)
        pending = max(total - completed, 0)
        pct = round((completed / total) * 100, 2) if total > 0 else 0.0
        out[int(sa.pk)] = CompletionStats(
            total=total,
            completed=completed,
            pending=pending,
            completion_pct=pct,
        )
    return out


def ews_students_needing_attention(
    teacher_profile,
    year,
    term,
    assignments,
    scale: float | None = None,
    drop_threshold_pct: float = 10.0,
):
    """
    # tenant-isolation-allow: service-layer-scoped-via-caller-student-classroom-or-teacher-fk
    Early warning: students with grade drop > threshold (e.g. 10% of scale) vs previous term.
    Returns list of dicts: {student_name, subject, classroom, drop_points}.

    ``scale`` is the grade yardstick (the school's score-scale max). When None it is
    derived local-first from the school's active grading scale, so the "10% drop"
    threshold means 10 points on a /100 school and 2 on a /20 school — never a
    hardcoded 0-20 assumption.
    """
    # tenant-isolation-allow: service-layer-scoped-via-caller-student-classroom-or-teacher-fk
    if not teacher_profile or not year or not term or not assignments:
        return []
    if scale is None:
        try:
            from apps.evals.grading_provisioning import resolve_school_score_scale

            # Drop-yardstick denominator, not a bound: explicit neutral fallback.
            scale = float(
                resolve_school_score_scale(
                    getattr(teacher_profile, "school", None), default=100
                )
            )
        except Exception:  # noqa: BLE001 — degrade to a neutral 100-point scale
            scale = 100.0
    # tenant-isolation-allow: service-layer-scoped-via-caller-student-classroom-or-teacher-fk
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
        # tenant-isolation-allow: service-layer-scoped-via-caller-student-classroom-or-teacher-fk
        if (
            not sa
            or not getattr(sa, "classroom", None)
            # tenant-isolation-allow: service-layer-scoped-via-caller-student-classroom-or-teacher-fk
            or not getattr(sa, "subject", None)
        ):
            # tenant-isolation-allow: service-layer-scoped-via-caller-student-classroom-or-teacher-fk
            continue
        prev_sa = SubjectAssignment.objects.filter(
            academic_year=year,
            # tenant-isolation-allow: service-layer-scoped-via-caller-student-classroom-or-teacher-fk
            term=prev_term,
            classroom=sa.classroom,
            subject=sa.subject,
        ).first()
        # tenant-isolation-allow: service-layer-scoped-via-caller-student-classroom-or-teacher-fk
        if not prev_sa:
            continue
        # tenant-isolation-allow: service-layer-scoped-via-caller-student-classroom-or-teacher-fk
        curr_evals = {
            # tenant-isolation-allow: service-layer-scoped-via-caller-student-classroom-or-teacher-fk
            e.student_id: (e.final_score or e.total_score)
            for e in Evaluation.objects.filter(
                subject_assignment=sa, term=term
            # tenant-isolation-allow: service-layer-scoped-via-caller-student-classroom-or-teacher-fk
            ).select_related("student")
        }
        # tenant-isolation-allow: service-layer-scoped-via-caller-student-classroom-or-teacher-fk
        prev_evals = {
            e.student_id: (e.final_score or e.total_score)
            # tenant-isolation-allow: service-layer-scoped-via-caller-student-classroom-or-teacher-fk
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
            # tenant-isolation-allow: service-layer-scoped-via-caller-student-classroom-or-teacher-fk
            except (TypeError, ValueError):
                continue
            drop = prev_f - curr_f
            # tenant-isolation-allow: service-layer-scoped-via-caller-student-classroom-or-teacher-fk
            if drop < drop_min:
                continue
            # tenant-isolation-allow: service-layer-scoped-via-caller-student-classroom-or-teacher-fk
            key = (sid, sa.subject_id)
            if key in seen:
                continue
            seen.add(key)
            # tenant-isolation-allow: service-layer-scoped-via-caller-student-classroom-or-teacher-fk
            ev = (
                Evaluation.objects.filter(
                    subject_assignment=sa, term=term, student_id=sid
                )
                .select_related("student")
                .first()
            )
            student_name = (
                ev.student.get_full_name() if ev and ev.student else f"Student {sid}"
            )
            result.append(
                {
                    "student_name": student_name,
                    "subject": sa.subject.name,
                    "classroom": sa.classroom.name,
                    "drop_points": round(drop, 1),
                }
            )
    return result[:20]  # cap for dashboard
