"""
Pass 13.D: at-risk model loader + predict interface with heuristic default.

Production path: training notebook (apps/analytics/ml/training/) saves a
pickled estimator to a path read from `settings.AT_RISK_MODEL_PATH` (or
env). On load, this module wraps it with a stable predict() that always
returns (score 0-100, reason_summary, model_version).

When no artifact is present, predict() uses the existing rule-based
heuristic so the nightly pipeline keeps producing reason-summaries for
every tenant from day one.

The model artifact contract:
  - `predict_proba(X)` for sklearn-compatible estimators, OR
  - `predict(X)` returning a 0..100 score directly.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Optional

from django.conf import settings

from .at_risk_features import AtRiskFeatures, extract_features

logger = logging.getLogger(__name__)

_MODEL_CACHE: dict[str, Any] = {}


def _model_path() -> str:
    return (
        getattr(settings, "AT_RISK_MODEL_PATH", None)
        or os.environ.get("AT_RISK_MODEL_PATH")
        or ""
    ).strip()


def _load_model():
    """Lazy-load the pickled model artifact. Cached per-process.

    The artifact may be either:

    * a bare sklearn-compatible estimator (legacy shape), or
    * a dict bundle produced by ``apps.analytics.ml.train_at_risk`` with
      keys ``{"model", "feature_order", "model_version", "training"}``
      (current shape — Wave K3 verified).

    In the bundle case we unwrap the estimator and stash the
    ``model_version`` on it (as a plain attribute) so downstream code
    that reads ``getattr(model, "model_version", None)`` keeps working
    without further plumbing.
    """
    path = _model_path()
    if not path:
        return None
    if "model" in _MODEL_CACHE:
        return _MODEL_CACHE["model"]
    try:
        import joblib

        loaded = joblib.load(path)
    except (ImportError, FileNotFoundError, OSError, ValueError) as exc:
        logger.warning("at_risk_model: failed to load artifact %s: %s", path, exc)
        _MODEL_CACHE["model"] = None
        return None
    if isinstance(loaded, dict) and "model" in loaded:
        estimator = loaded["model"]
        # Surface the bundle's model_version on the estimator so the
        # existing reader in predict_at_risk() does not need to know
        # about the bundle shape.
        version = loaded.get("model_version")
        if version and not hasattr(estimator, "model_version"):
            try:
                estimator.model_version = version
            except (AttributeError, TypeError):
                # Some estimators forbid attr-set; leave fallback path
                # (artifact basename) to predict_at_risk().
                pass
        model = estimator
    else:
        model = loaded
    _MODEL_CACHE["model"] = model
    return model


def _heuristic_score(features: AtRiskFeatures) -> tuple[float, str]:
    """
    Default heuristic when no ML model is loaded. Mirrors (and replaces) the
    `pct_absent * 0.4 + 20` pattern but uses the wider feature set so the
    fallback already produces better signals than the original baseline.
    """
    score = 30.0
    reasons: list[str] = []
    if features.attendance_rate < 0.85:
        score += (0.85 - features.attendance_rate) * 100
        reasons.append(f"attendance {int(features.attendance_rate * 100)}%")
    if features.avg_evaluation_score and features.avg_evaluation_score < 60:
        score += (60 - features.avg_evaluation_score)
        reasons.append(f"avg score {round(features.avg_evaluation_score, 1)}")
    if features.eval_score_trend < -5:
        score += min(20, abs(features.eval_score_trend))
        reasons.append(f"trend {round(features.eval_score_trend, 1)}")
    if features.open_balance_amount and features.open_balance_amount > 0:
        score += min(15, features.open_balance_amount / 100)
        reasons.append(f"open balance {round(features.open_balance_amount, 0)}")
    if features.days_since_last_login > 30:
        score += min(15, features.days_since_last_login / 30)
        reasons.append(f"last login {features.days_since_last_login}d ago")
    score = max(0.0, min(100.0, score))
    reason = (
        f"Risk drivers: {'; '.join(reasons)}." if reasons else "No notable risk signals."
    )
    return round(score, 2), reason


def _model_score(model, features: AtRiskFeatures) -> Optional[float]:
    """Try predict_proba then predict; never raise."""
    try:
        X = [features.as_vector()]
        if hasattr(model, "predict_proba"):
            proba = model.predict_proba(X)
            # Assume binary classifier: P(at_risk=True) * 100.
            return float(proba[0][-1]) * 100.0
        if hasattr(model, "predict"):
            return float(model.predict(X)[0])
    except Exception as exc:  # noqa: BLE001
        logger.warning("at_risk_model: predict failed (%s) — falling back", exc)
    return None


def predict_at_risk(student) -> tuple[float, str, Optional[str]]:
    """
    Return `(score, reason_summary, model_version)`. Falls back to the
    heuristic on any failure so the nightly batch always produces output.
    """
    features = extract_features(student)
    model = _load_model()
    if model is not None:
        ml_score = _model_score(model, features)
        if ml_score is not None:
            score = max(0.0, min(100.0, ml_score))
            heuristic_reason = _heuristic_score(features)[1]
            model_version = (
                getattr(model, "model_version", None)
                or os.path.basename(_model_path())
                or "ml-v1"
            )
            return round(score, 2), heuristic_reason, str(model_version)
    score, reason = _heuristic_score(features)
    return score, reason, None
