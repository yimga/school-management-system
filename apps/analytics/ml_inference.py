"""Risk inference compatibility layer used by the nightly scoring command."""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Optional

from .models import MLModel


def get_active_model(
    model_type: str = "risk", name: Optional[str] = None
) -> Optional[MLModel]:
    """Return the active ML model for the given type (and optional name)."""
    qs = MLModel.objects.filter(model_type=model_type, is_active=True)
    if name:
        qs = qs.filter(name=name)
    return qs.order_by("-created_at").first()


def run_risk_inference(
    school_id: str,
    student_data: dict[str, Any],
    model: Optional[MLModel] = None,
) -> tuple[Decimal, str, Optional[str]]:
    """
    Run risk scoring. Returns (score 0-100, reason_summary, model_version).
    The canonical predictor loads the promoted artifact and falls back to the
    governed heuristic when no usable artifact is available.
    """
    from apps.people.models import StudentProfile
    from .ml.at_risk_model import predict_at_risk

    student_id = student_data.get("id") or student_data.get("student_id")
    if not student_id:
        return (Decimal("0"), "", None)
    student = StudentProfile.objects.filter(
        pk=student_id,
        school_id=school_id,
        is_active=True,
    ).first()
    if student is not None:
        score, reason, model_version = predict_at_risk(student)
        return (Decimal(str(score)), (reason or "")[:500], model_version)
    return (Decimal("0"), "", None)


def run_risk_inference_batch(
    school_id: str, threshold: int = 50
) -> list[tuple[Any, Decimal, str, Optional[str]]]:
    """
    Score every active student in one school through the canonical predictor.

    ``threshold`` remains for call compatibility; banding is applied by the
    persistence/reporting layer, not by dropping green students before scoring.
    """
    del threshold
    from apps.people.models import StudentProfile
    from .ml.at_risk_model import predict_at_risk

    students = StudentProfile.objects.filter(
        school_id=school_id,
        is_active=True,
    ).select_related(
        "user",
        "school",
        "classroom",
        "academic_year",
    )
    out: list[tuple[Any, Decimal, str, Optional[str]]] = []
    for student in students.iterator(chunk_size=250):
        score, reason, model_version = predict_at_risk(student)
        out.append(
            (
                student,
                Decimal(str(score)),
                (reason or "")[:500],
                model_version,
            )
        )
    return out
