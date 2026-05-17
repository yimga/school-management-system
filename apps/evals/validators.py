"""Grade validation and conversion utilities."""

from decimal import Decimal
from statistics import mean, stdev
from typing import Dict, List
import logging

from apps.platform_runtime.structured_logging import log_exception_with_context

logger = logging.getLogger(__name__)

# Typed exceptions for validation detection (outlier, jump, duplicate remark).
# Covers attribute access, numeric/statistics, and ORM.
try:
    from django.db import DatabaseError

    _EVAL_VALIDATION_DETECTION_ERRORS = (
        TypeError,
        ValueError,
        ZeroDivisionError,
        AttributeError,
        KeyError,
        DatabaseError,
    )
except ImportError:
    _EVAL_VALIDATION_DETECTION_ERRORS = (
        TypeError,
        ValueError,
        ZeroDivisionError,
        AttributeError,
        KeyError,
    )


class GradeValidator:
    """Validates grade entries against business rules."""

    VALIDATION_ERRORS = {
        "score_out_of_range": "Score exceeds maximum scale",
        "negative_score": "Score cannot be negative",
        "outlier_detected": "Score >2σ from class mean",
        "impossible_jump": "Grade changed dramatically",
        "duplicate_remark": "Remark identical to 3+ students",
        "missing_required_component": "Required component missing",
    }

    def __init__(self, score_scale: Decimal = Decimal("20.00")):
        self.score_scale = score_scale

    def validate_single_score(self, score: Decimal) -> List[str]:
        """Returns list of error codes."""
        errors = []

        if score is None:
            return errors

        if score < 0:
            errors.append("negative_score")

        if score > self.score_scale:
            errors.append("score_out_of_range")

        return errors

    def validate_evaluation(self, evaluation, weights) -> Dict:
        """Complete validation of Evaluation instance."""
        errors = []
        flags = {}

        # Validate score ranges
        for component in [
            "seq1_score",
            "seq2_score",
            "exam_score",
            "mock_score",
            "practical_score",
        ]:
            score = getattr(evaluation, component)
            errs = self.validate_single_score(score)
            errors.extend(errs)
            if errs:
                flags[component] = True

        # Check required components
        required_components = {
            "seq1_score": weights.seq1_weight,
            "seq2_score": weights.seq2_weight,
            "exam_score": weights.exam_weight,
            "mock_score": weights.mock_weight,
            "practical_score": weights.practical_weight,
        }

        for component, weight in required_components.items():
            if weight > 0 and getattr(evaluation, component) is None:
                errors.append("missing_required_component")
                flags[component] = True

        # Detect outliers
        try:
            if self._detect_outlier(evaluation, weights):
                errors.append("outlier_detected")
                flags["outlier"] = True
        except _EVAL_VALIDATION_DETECTION_ERRORS:
            school_id = getattr(evaluation, "school_id", None)
            log_exception_with_context(
                "Outlier detection failed",
                school_id=school_id,
                extra={
                    "evaluation_id": getattr(evaluation, "pk", None),
                    "section": "outlier",
                },
            )

        # Check term-over-term jumps
        try:
            if self._detect_impossible_jump(evaluation):
                errors.append("impossible_jump")
                flags["impossible_jump"] = True
        except _EVAL_VALIDATION_DETECTION_ERRORS:
            school_id = getattr(evaluation, "school_id", None)
            log_exception_with_context(
                "Jump detection failed",
                school_id=school_id,
                extra={
                    "evaluation_id": getattr(evaluation, "pk", None),
                    "section": "impossible_jump",
                },
            )

        # Check duplicate remarks
        try:
            if self._detect_duplicate_remark(evaluation):
                errors.append("duplicate_remark")
                flags["duplicate_remark"] = True
        except _EVAL_VALIDATION_DETECTION_ERRORS:
            school_id = getattr(evaluation, "school_id", None)
            log_exception_with_context(
                "Duplicate remark check failed",
                school_id=school_id,
                extra={
                    "evaluation_id": getattr(evaluation, "pk", None),
                    "section": "duplicate_remark",
                },
            )

        return {
            "is_valid": len(errors) == 0,
            "errors": errors,
            "flags": flags,
        }

    def _detect_outlier(self, evaluation, weights) -> bool:
        """Check if final_score is >2σ from class mean."""
        score = (
            evaluation.final_score
            if evaluation.final_score is not None
            else evaluation.total_score
        )
        if score is None:
            return False

        from apps.evals.models import Evaluation

        sibling_evals = (
            # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
            Evaluation.objects.filter(
                academic_year=evaluation.academic_year,
                term=evaluation.term,
                subject_assignment=evaluation.subject_assignment,
            )
            .values_list("final_score", flat=True)
            .exclude(pk=evaluation.pk)
        )

        scores = [float(s) for s in sibling_evals if s is not None]

        if len(scores) < 3:
            return False

        try:
            mean_score = mean(scores)
            std_dev = stdev(scores)
            if std_dev == 0:
                return False
            z_score = abs((float(score) - mean_score) / std_dev)
            return z_score > 2.0
        except (TypeError, ValueError, ZeroDivisionError):
            return False

    def _detect_impossible_jump(self, evaluation) -> bool:
        """Check if grade jumped >50% from previous term."""
        current_score = (
            evaluation.final_score
            if evaluation.final_score is not None
            else evaluation.total_score
        )
        if current_score is None:
            return False

        from apps.academics.models import Term
        from apps.evals.models import Evaluation

        # Get previous term
        # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
        prev_terms = Term.objects.filter(
            academic_year=evaluation.academic_year
        ).order_by("-id")

        if not prev_terms.exists():
            return False
# tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17

        prev_eval = Evaluation.objects.filter(
            student=evaluation.student,
            subject_assignment=evaluation.subject_assignment,
            term__in=prev_terms[:1],
        ).first()

        prev_score = (
            prev_eval.final_score
            if prev_eval and prev_eval.final_score is not None
            else (prev_eval.total_score if prev_eval else None)
        )
        if not prev_eval or prev_score is None:
            return False

        if float(prev_score) == 0:
            return False

        pct_change = abs((float(current_score) - float(prev_score)) / float(prev_score))
        return pct_change > 0.5

    def _detect_duplicate_remark(self, evaluation) -> bool:
        """Check if remark is identical to 3+ other students."""
        if not evaluation.remarks or len(evaluation.remarks) < 5:
            return False

        # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
        from apps.evals.models import Evaluation

        dup_count = (
            # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
            Evaluation.objects.filter(
                academic_year=evaluation.academic_year,
                term=evaluation.term,
                subject_assignment__classroom=evaluation.subject_assignment.classroom,
                remarks=evaluation.remarks,
            )
            .exclude(pk=evaluation.pk)
            .count()
        )

        return dup_count >= 3


class GradeConverter:
    """Converts numeric grades to letter grades, GPA, percentages."""

    def __init__(self, weights):
        self.weights = weights

    def numeric_to_letter(self, numeric_score: Decimal) -> str:
        """Converts 0–20 to A–E."""
        if numeric_score is None:
            return ""

        score = float(numeric_score)

        if score >= float(self.weights.grade_a_min):
            return "A"
        elif score >= float(self.weights.grade_b_min):
            return "B"
        elif score >= float(self.weights.grade_c_min):
            return "C"
        elif score >= float(self.weights.grade_d_min):
            return "D"
        elif score >= float(self.weights.grade_e_min):
            return "E"
        else:
            return ""

    def numeric_to_gpa(self, numeric_score: Decimal) -> float:
        """Converts 0–20 to 4.0 GPA scale."""
        if numeric_score is None:
            return 0.0
        return (float(numeric_score) / 20.0) * 4.0

    def numeric_to_percentage(self, numeric_score: Decimal) -> float:
        """Converts 0–20 to 0–100%."""
        if numeric_score is None:
            return 0.0
        return (float(numeric_score) / 20.0) * 100.0

    def convert(self, numeric_score: Decimal) -> Dict:
        """Returns all conversion formats."""
        return {
            "numeric": numeric_score,
            "letter": self.numeric_to_letter(numeric_score),
            "gpa": self.numeric_to_gpa(numeric_score),
            "percentage": self.numeric_to_percentage(numeric_score),
        }
