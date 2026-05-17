"""Grade-prediction inference: heuristic baseline + ML artifact loader.

Pattern mirrors `at_risk_model.py`. Loader resolves via
`GradePredictionModelArtifact.current_production()` first; falls back
to `GRADE_PREDICTION_MODEL_PATH` env/setting. Cache is path-keyed so
promotes take effect without worker restart.

Heuristic baseline (when no model is loaded): weighted blend of
prior-term mean and mid-term avg, attenuated by attendance penalty.
This is the day-zero contract for new tenants — predictions go out
from the very first term, before any labels exist.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Optional

from django.conf import settings

from .grade_prediction_features import (
    GradePredictionFeatures,
    extract_grade_prediction_features,
)

logger = logging.getLogger(__name__)

_MODEL_CACHE: dict[str, Any] = {}

_GRADE_PRED_FEATURE_NAMES = (
    "prior_mean_score",
    "mid_term_avg",
    "mid_term_count",
    "attendance_rate",
    "absence_count",
    "eval_trend",
    "incident_count",
    "days_in_term_so_far",
)


def _registry_artifact():
    try:
        from apps.analytics.models import GradePredictionModelArtifact
    except (ImportError, AttributeError):
        return None
    try:
        return GradePredictionModelArtifact.current_production()
    except Exception as exc:  # noqa: BLE001 — DB may be unmigrated / locked
        logger.debug("grade_prediction_model: registry lookup failed (%s)", exc)
        return None


def _model_path() -> str:
    art = _registry_artifact()
    if art and art.artifact_path:
        return art.artifact_path.strip()
    return (
        getattr(settings, "GRADE_PREDICTION_MODEL_PATH", None)
        or os.environ.get("GRADE_PREDICTION_MODEL_PATH")
        or ""
    ).strip()


def _load_model():
    path = _model_path()
    if not path:
        return None
    cache_key = f"grade_pred_model::{path}"
    if cache_key in _MODEL_CACHE:
        return _MODEL_CACHE[cache_key]
    try:
        import joblib
        loaded = joblib.load(path)
    except (ImportError, FileNotFoundError, OSError, ValueError) as exc:
        logger.warning("grade_prediction_model: load failed %s: %s", path, exc)
        _MODEL_CACHE[cache_key] = None
        return None
    if isinstance(loaded, dict) and "model" in loaded:
        model = loaded["model"]
        version = loaded.get("model_version")
        if version and not hasattr(model, "model_version"):
            try:
                model.model_version = version
            except (AttributeError, TypeError):
                pass
    else:
        model = loaded
    _MODEL_CACHE[cache_key] = model
    art = _registry_artifact()
    if art and art.model_version:
        try:
            model.model_version = art.model_version
        except (AttributeError, TypeError):
            pass
    return model


def _heuristic_predict(features: GradePredictionFeatures) -> tuple[float, str]:
    """Blend prior + mid-term avg with attendance penalty.

    Weights chosen so a new student (no prior, no mid-term) lands at
    the platform default (≈60). The output is clipped to [0, 100].
    """
    have_mid = features.mid_term_count > 0
    if have_mid:
        # Once mid-term evidence exists, weight it 70/30 vs prior.
        base = 0.7 * features.mid_term_avg + 0.3 * features.prior_mean_score
    else:
        base = features.prior_mean_score
    # Attendance penalty kicks in below 90% (each missing percentage point
    # below 90 costs 0.5 grade points). Caps at 10 points off.
    penalty = 0.0
    if features.attendance_rate < 0.90:
        penalty = min(10.0, (0.90 - features.attendance_rate) * 100 * 0.5)
    base -= penalty
    # Trend nudge.
    base += max(-5.0, min(5.0, features.eval_trend * 0.4))
    base = max(0.0, min(100.0, base))
    reason_parts = []
    if features.mid_term_count > 0:
        reason_parts.append(
            f"mid-term avg {features.mid_term_avg:.1f} ({features.mid_term_count} evals)"
        )
    if features.prior_mean_score:
        reason_parts.append(f"prior term {features.prior_mean_score:.1f}")
    if penalty > 0:
        reason_parts.append(
            f"attendance {int(features.attendance_rate * 100)}% (-{penalty:.1f})"
        )
    if features.eval_trend:
        reason_parts.append(f"trend {features.eval_trend:+.1f}")
    reason = (
        "Heuristic drivers: " + "; ".join(reason_parts) + "."
        if reason_parts else "Insufficient signal; default cohort grade."
    )
    return round(base, 2), reason


def _model_predict(model, features: GradePredictionFeatures) -> Optional[float]:
    try:
        X = [features.as_vector()]
        if hasattr(model, "predict"):
            return float(model.predict(X)[0])
    except Exception as exc:  # noqa: BLE001 — nightly must never crash on predict
        logger.warning("grade_prediction_model: predict failed (%s) — fallback", exc)
    return None


def _load_at_path(path: str):
    """Load a joblib bundle by explicit path; bypasses the registry.

    Used by the shadow command to score with prod + candidate
    simultaneously. Shares the path-keyed cache with `_load_model`.
    """
    if not path:
        return None
    cache_key = f"grade_pred_model::{path}"
    if cache_key in _MODEL_CACHE:
        return _MODEL_CACHE[cache_key]
    try:
        import joblib
        loaded = joblib.load(path)
    except (ImportError, FileNotFoundError, OSError, ValueError) as exc:
        logger.warning("grade_prediction_model: explicit load failed %s: %s", path, exc)
        _MODEL_CACHE[cache_key] = None
        return None
    if isinstance(loaded, dict) and "model" in loaded:
        model = loaded["model"]
        version = loaded.get("model_version")
        if version and not hasattr(model, "model_version"):
            try:
                model.model_version = version
            except (AttributeError, TypeError):
                pass
    else:
        model = loaded
    _MODEL_CACHE[cache_key] = model
    return model


def predict_grade_with_artifact(
    student, subject, term, artifact_path: str,
) -> float | None:
    """Score one (student, subject, term) against an explicit artifact.

    Returns the predicted grade or None on any failure — does NOT fall
    back to heuristic.
    """
    model = _load_at_path(artifact_path)
    if model is None:
        return None
    features = extract_grade_prediction_features(student, subject, term)
    return _model_predict(model, features)


def predict_grade(student, subject, term) -> dict[str, Any]:
    """Return a dict with predicted_grade, reason, confidence band, model_version.

    Heuristic always runs (cheap; gives the confidence-band fallback).
    The ML model overrides the predicted_grade and reason when available;
    confidence bands stay heuristic since regression models typically
    don't expose calibrated intervals without extra plumbing.
    """
    features = extract_grade_prediction_features(student, subject, term)
    heuristic_score, heuristic_reason = _heuristic_predict(features)
    confidence_low = max(0.0, heuristic_score - 8.0)
    confidence_high = min(100.0, heuristic_score + 8.0)

    model = _load_model()
    if model is not None:
        ml_score = _model_predict(model, features)
        if ml_score is not None:
            ml_score = max(0.0, min(100.0, ml_score))
            model_version = (
                getattr(model, "model_version", None)
                or os.path.basename(_model_path())
                or "grade-v1"
            )
            return {
                "predicted_grade": round(ml_score, 2),
                "reason_summary": heuristic_reason,
                "confidence_low": confidence_low,
                "confidence_high": confidence_high,
                "model_version": str(model_version),
                "features": features.as_dict(),
            }
    return {
        "predicted_grade": heuristic_score,
        "reason_summary": heuristic_reason,
        "confidence_low": confidence_low,
        "confidence_high": confidence_high,
        "model_version": "",
        "features": features.as_dict(),
    }
