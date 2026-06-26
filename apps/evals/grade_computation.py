"""Live grade-path computation — wires the polymorphic formula engine into Evaluation."""

from __future__ import annotations

from typing import Any

from apps.evals.grading_formula_engine import (
    GradingFormulaError,
    PRESET_GRADING_FORMULAS,
    evaluate_grading_formula,
)
from apps.platform_runtime.structured_logging import log_exception_with_context

# ScaleType / AssessmentWeights.grading_scale → PRESET_GRADING_FORMULAS key.
_SCALE_TYPE_TO_PRESET_KEY: dict[str, str] = {
    "numeric_0_20": "francophone_0_20",
    "gpa_4_0": "us_gpa_4",
    "waec_letter": "waec_aggregate",
    "percentage": "waec_aggregate",
    "letter_a_e": "uk_gcse_points",
}


def _resolve_formula_text(weights: Any, school: Any | None) -> str:
    """Resolve tenant formula text from the school's default GradingScale only."""
    if school is None or not getattr(school, "pk", None):
        return ""
    try:
        from apps.evals.models import GradingScale

        scale = (
            GradingScale.objects.filter(school=school, is_default=True, is_active=True)
            .order_by("-id")
            .first()
        )
        if scale is None:
            return ""
        cfg = scale.config if isinstance(scale.config, dict) else {}
        text = str(cfg.get("formula_text") or "").strip()
        if text:
            return text
        preset_key = _SCALE_TYPE_TO_PRESET_KEY.get(str(scale.scale_type or ""), "")
        if preset_key:
            return PRESET_GRADING_FORMULAS.get(preset_key, "") or ""
    except Exception as exc:  # noqa: BLE001 — best-effort scale lookup
        log_exception_with_context(
            "grade_computation: GradingScale formula lookup failed",
            school_id=str(getattr(school, "pk", None)),
            extra={"error": str(exc)},
        )
    return ""


def _component_values(evaluation: Any) -> dict[str, float]:
    s1 = evaluation.seq1_score if evaluation.seq1_score is not None else evaluation.test1
    s2 = evaluation.seq2_score if evaluation.seq2_score is not None else evaluation.test2
    seq1 = float(s1) if s1 is not None else 0.0
    seq2 = float(s2) if s2 is not None else 0.0
    exam = float(evaluation.exam_score) if evaluation.exam_score is not None else 0.0
    mock = float(evaluation.mock_score) if evaluation.mock_score is not None else 0.0
    practical = (
        float(evaluation.practical_score)
        if evaluation.practical_score is not None
        else 0.0
    )
    return {
        "seq1": seq1,
        "seq2": seq2,
        "exam": exam,
        "mock": mock,
        "practical": practical,
        "coursework": seq1 + seq2,
    }


def weighted_average_total(evaluation: Any, weights: Any) -> float:
    """Legacy weighted-mean path (unchanged behaviour when no formula is configured)."""
    components = _component_values(evaluation)
    pairs = (
        (components["seq1"], weights.seq1_weight),
        (components["seq2"], weights.seq2_weight),
        (components["exam"], weights.exam_weight),
        (components["mock"], weights.mock_weight),
        (components["practical"], weights.practical_weight),
    )
    total_w = 0
    total = 0.0
    for val, w in pairs:
        if w <= 0:
            continue
        total_w += w
        total += val * w
    if total_w <= 0:
        return 0.0
    return round(total / total_w, 2)


def compute_evaluation_total_score(evaluation: Any, weights: Any | None = None) -> float:
    """Compute total_score for an Evaluation — formula engine when configured."""
    from apps.evals.models import AssessmentWeights

    if weights is None:
        weights = AssessmentWeights.get_for(
            evaluation.academic_year,
            evaluation.subject_assignment.classroom
            if evaluation.subject_assignment_id
            else None,
            evaluation.term,
        )

    school = None
    if evaluation.subject_assignment_id and getattr(
        evaluation.subject_assignment, "classroom", None
    ):
        school = getattr(evaluation.subject_assignment.classroom, "school", None)
    if school is None:
        school = getattr(evaluation, "school", None)

    formula_text = _resolve_formula_text(weights, school)
    if not formula_text:
        return weighted_average_total(evaluation, weights)

    variables = _component_values(evaluation)
    scale_key = str(getattr(weights, "grading_scale", "") or "custom")
    try:
        result = evaluate_grading_formula(
            formula_text=formula_text,
            variables=variables,
            scale_key=scale_key,
        )
        return round(float(result.value), 2)
    except GradingFormulaError as exc:
        log_exception_with_context(
            "grade_computation: formula evaluation failed; falling back to weighted mean",
            school_id=str(getattr(school, "pk", None)),
            extra={
                "evaluation_id": getattr(evaluation, "pk", None),
                "formula_text": formula_text[:120],
                "error": str(exc),
            },
        )
        return weighted_average_total(evaluation, weights)
