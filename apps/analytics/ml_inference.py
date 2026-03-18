"""
Phase 9: ML inference — load active model from registry and run prediction (e.g. risk score).
compute_nightly_risk uses this and records model_version on RiskFactor.
"""

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
    If no model in registry, falls back to rule-based (AdvancedAnalyticsService).
    """
    model_version = None
    if model:
        model_version = f"{model.name}@{model.version}"
        # Optional: load artifact and run real inference (e.g. pickle/joblib).
        # For now we use config threshold and fall through to rule-based.
        threshold = (model.config or {}).get("threshold", 50)
    else:
        threshold = 50

    # Fallback: use existing rule-based risk (no artifact loading in this stub).
    from .services import AdvancedAnalyticsService

    at_risk_list = AdvancedAnalyticsService.identify_at_risk_students(
        school_id=school_id,
        threshold=threshold,
    )
    student_id = student_data.get("id") or student_data.get("student_id")
    for item in at_risk_list:
        sid = getattr(item, "id", None) or (
            item.get("id") if isinstance(item, dict) else None
        )
        if sid == student_id:
            score = Decimal(str(getattr(item, "risk_score", 60) or 60))
            reason = (
                getattr(item, "risk_reason_summary", None)
                or (item.get("risk_reason_summary") if isinstance(item, dict) else None)
                or "At-risk (attendance/grades/fees)"
            )
            return (score, reason[:500] if reason else "", model_version)
    return (Decimal("0"), "", model_version)


def run_risk_inference_batch(
    school_id: str, threshold: int = 50
) -> list[tuple[Any, Decimal, str, Optional[str]]]:
    """
    Run risk for all at-risk students in school. Returns list of (student, score, reason, model_version).
    Used by compute_nightly_risk.
    """
    model = get_active_model("risk")
    model_version = f"{model.name}@{model.version}" if model else None
    from .services import AdvancedAnalyticsService

    at_risk = AdvancedAnalyticsService.identify_at_risk_students(
        school_id=school_id, threshold=threshold
    )
    out = []
    for student in at_risk:
        score = Decimal(str(getattr(student, "risk_score", None) or 60))
        reason = (
            getattr(student, "risk_reason_summary", None)
            or "At-risk (attendance/grades/fees)"
        )
        out.append((student, score, reason[:500] if reason else "", model_version))
    return out
