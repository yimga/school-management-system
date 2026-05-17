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


def _registry_artifact():
    """Return the current PRODUCTION `AtRiskModelArtifact` row, or None.

    The registry is the authoritative source. If the analytics app is not
    yet migrated (early tests, fresh checkout), or there's no production
    row, return None so the env-var fallback wins. We never want this
    helper to crash the inference path.
    """
    try:
        from apps.analytics.models import AtRiskModelArtifact
    except (ImportError, AttributeError):
        return None
    try:
        return AtRiskModelArtifact.current_production()
    except Exception as exc:  # noqa: BLE001 — DB may be unmigrated, locked, or unreachable
        logger.debug("at_risk_model: registry lookup failed (%s); using env path", exc)
        return None


def _model_path() -> str:
    """Resolve the artifact path the loader should serve.

    Precedence:
      1. Registry's current PRODUCTION row (`AtRiskModelArtifact.current_production`)
      2. `settings.AT_RISK_MODEL_PATH`
      3. `AT_RISK_MODEL_PATH` env var
    """
    artifact = _registry_artifact()
    if artifact and artifact.artifact_path:
        return artifact.artifact_path.strip()
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
    # Cache is keyed by path so a `promote_at_risk_artifact` flip takes
    # effect on the very next inference call without a worker restart.
    cache_key = f"model::{path}"
    if cache_key in _MODEL_CACHE:
        return _MODEL_CACHE[cache_key]
    try:
        import joblib

        loaded = joblib.load(path)
    except (ImportError, FileNotFoundError, OSError, ValueError) as exc:
        logger.warning("at_risk_model: failed to load artifact %s: %s", path, exc)
        _MODEL_CACHE[cache_key] = None
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
    _MODEL_CACHE[cache_key] = model
    # Prefer the registry's stable model_version when an artifact row
    # is live; that's the value joining to AtRiskInferenceRun + drift
    # snapshots, so it should win over the bundle's own string.
    registry_row = _registry_artifact()
    if registry_row and registry_row.model_version:
        try:
            model.model_version = registry_row.model_version
        except (AttributeError, TypeError):
            pass
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


_FEATURE_NAMES = (
    "attendance_rate",
    "absence_count",
    "late_count",
    "avg_evaluation_score",
    "evaluation_count",
    "eval_score_trend",
    "open_invoice_count",
    "open_balance_amount",
    "days_since_last_login",
)

# Heuristic "neutral baseline" for each feature — what an unremarkable
# student's value looks like. Used to classify a contribution's direction
# (above neutral = elevates risk, below = lowers). Doesn't have to be
# precise; only the sign matters for the direction tag.
_FEATURE_BASELINE = {
    "attendance_rate": 0.95,
    "absence_count": 1.0,
    "late_count": 1.0,
    "avg_evaluation_score": 70.0,
    "evaluation_count": 5.0,
    "eval_score_trend": 0.0,
    "open_invoice_count": 0.0,
    "open_balance_amount": 0.0,
    "days_since_last_login": 7.0,
}

# Features where HIGHER value = LOWER risk (inverse). Used to flip the
# direction tag so "elevates" / "lowers" reads correctly for operators.
_FEATURE_INVERSE_DIRECTION = {
    "attendance_rate",
    "avg_evaluation_score",
    "evaluation_count",
}


def _explain_via_shap(model, features) -> list[dict]:
    """Wave 10: per-row Shapley values via the `shap` library.

    Returns top-K contributions sorted by absolute SHAP value, with
    direction inferred from the SHAP sign (positive SHAP = elevates
    risk relative to baseline). Returns [] if `shap` isn't installed
    or the model isn't supported by `shap.TreeExplainer`.

    Cost: ~10-100× the cheap explainer. Only call when the operator
    opted into the full path.
    """
    try:
        import shap  # type: ignore
        import numpy as np
    except ImportError:
        return []
    try:
        explainer = shap.TreeExplainer(model)
        vector = features.as_vector()
        # SHAP requires ndarray input from 0.40+. Wrap as (1, n_features).
        X_in = np.array([vector], dtype=float)
        raw = explainer.shap_values(X_in)
        arr = np.asarray(raw)
        # Possible shapes from sklearn estimators:
        #   (1, n_features)                  — regression / single-output
        #   (2, 1, n_features)               — legacy binary classifier (list-of-2)
        #   (1, n_features, n_classes)       — SHAP 0.45+ binary classifier
        if arr.ndim == 2 and arr.shape[0] == 1:
            shap_vec = arr[0].tolist()
        elif arr.ndim == 3 and arr.shape[0] == 2:
            shap_vec = arr[1][0].tolist()  # positive class
        elif arr.ndim == 3 and arr.shape[-1] == 2:
            shap_vec = arr[0, :, 1].tolist()  # 0.45+ binary: last axis = class
        elif arr.ndim == 3 and arr.shape[-1] > 1:
            shap_vec = arr[0, :, -1].tolist()  # multiclass: take last class
        else:
            shap_vec = arr.flatten().tolist()
    except (AttributeError, TypeError, ValueError, IndexError, ImportError) as exc:
        logger.warning("explain_score: shap path failed (%s); returning []", exc)
        return []
    if len(shap_vec) != len(_FEATURE_NAMES):
        return []
    items = []
    for name, value, shap_val in zip(_FEATURE_NAMES, features.as_vector(), shap_vec):
        items.append({
            "name": name,
            "value": float(value),
            "importance": float(abs(shap_val)),
            "direction": "elevates" if shap_val > 0 else "lowers",
            "shap_value": float(shap_val),
        })
    items.sort(key=lambda d: d["importance"], reverse=True)
    return items


def explain_score(
    model, features, *, top_k: int = 3, method: str = "fast",
) -> list[dict]:
    """Return top-K feature attributions for one prediction.

    method="fast" (default) uses `model.feature_importances_` with
    `coef_` fallback — cheap, global-importance × per-row direction.

    method="shap" requires the `shap` library and computes true
    per-row Shapley values. ~10-100× slower per prediction. Falls
    back to the fast path when `shap` isn't installed.

    Format:
        [{"name": str, "value": float, "importance": float,
          "direction": "elevates"|"lowers", "shap_value": float?}]
    """
    if method == "shap":
        shap_items = _explain_via_shap(model, features)
        if shap_items:
            return shap_items[:max(0, top_k)]
        # Soft fall-through to fast path when shap isn't available
        # or the estimator can't be explained that way.
    vector = features.as_vector()
    if len(vector) != len(_FEATURE_NAMES):
        # Defensive: feature contract has drifted. Don't crash inference.
        return []

    importances: list[float] = []
    if hasattr(model, "feature_importances_"):
        try:
            raw = list(model.feature_importances_)
            if len(raw) == len(_FEATURE_NAMES):
                importances = [float(x) for x in raw]
        except (TypeError, ValueError, AttributeError):
            importances = []
    if not importances and hasattr(model, "coef_"):
        try:
            coef = model.coef_
            if hasattr(coef, "tolist"):
                coef = coef.tolist()
            # Multiclass: first row; binary: list-of-one-list
            if coef and isinstance(coef[0], (list, tuple)):
                coef = list(coef[0])
            if len(coef) == len(_FEATURE_NAMES):
                importances = [abs(float(c)) for c in coef]
        except (TypeError, ValueError, AttributeError):
            importances = []
    if not importances:
        return []

    items = []
    for name, value, importance in zip(_FEATURE_NAMES, vector, importances):
        baseline = _FEATURE_BASELINE.get(name, 0.0)
        delta = value - baseline
        if name in _FEATURE_INVERSE_DIRECTION:
            delta = -delta
        direction = "elevates" if delta > 0 else "lowers"
        items.append({
            "name": name,
            "value": float(value),
            "importance": float(importance),
            "direction": direction,
        })
    items.sort(key=lambda d: d["importance"], reverse=True)
    return items[:max(0, top_k)]


def _format_contribution_reason(contributions: list[dict]) -> str:
    """Build a human reason string from top contributions.

    Example:
        "Top model drivers: attendance_rate=0.62 (elevates, 31%); "
        "avg_evaluation_score=54.0 (elevates, 22%); ..."
    """
    if not contributions:
        return ""
    parts = []
    for c in contributions:
        parts.append(
            f"{c['name']}={c['value']:.2f} "
            f"({c['direction']}, {c['importance'] * 100:.0f}%)"
        )
    return "Top model drivers: " + "; ".join(parts) + "."


def _load_at_path(path: str):
    """Load a joblib bundle at an explicit path, bypassing the registry.

    Used by Wave 2 shadow scoring where we need both the production AND
    a candidate artifact loaded simultaneously — the registry-driven
    `_load_model` only ever resolves one. Cache is shared with the
    primary loader (path-keyed), so a path that's already live in
    production isn't paid for twice.
    """
    if not path:
        return None
    cache_key = f"model::{path}"
    if cache_key in _MODEL_CACHE:
        return _MODEL_CACHE[cache_key]
    try:
        import joblib
        loaded = joblib.load(path)
    except (ImportError, FileNotFoundError, OSError, ValueError) as exc:
        logger.warning("at_risk_model: explicit load failed for %s: %s", path, exc)
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


def predict_with_artifact(student, artifact_path: str) -> Optional[float]:
    """Score one student against an explicit artifact path. Returns score 0-100
    or None if the artifact can't be loaded / the predict call fails.

    This is the shadow-scoring entry point. It deliberately does NOT
    fall back to the heuristic — a missing candidate means "no
    comparison this time," not "produce a score from somewhere else."
    """
    model = _load_at_path(artifact_path)
    if model is None:
        return None
    features = extract_features(student)
    raw = _model_score(model, features)
    if raw is None:
        return None
    return max(0.0, min(100.0, raw))


def predict_at_risk(student) -> tuple[float, str, Optional[str]]:
    """
    Return `(score, reason_summary, model_version)`. Falls back to the
    heuristic on any failure so the nightly batch always produces output.

    Wave 3: when the ML path serves the score AND the model exposes
    `feature_importances_` / `coef_`, the reason_summary is now derived
    from top-3 contributions rather than the canned heuristic text.
    Use `predict_at_risk_with_explanation` to get the structured
    contributions list alongside.
    """
    score, reason, version, _contributions = predict_at_risk_with_explanation(student)
    return score, reason, version


def predict_at_risk_with_explanation(
    student,
) -> tuple[float, str, Optional[str], list[dict]]:
    """Like `predict_at_risk` but also returns the explanation list.

    Returns `(score, reason_summary, model_version, contributions)`.
    The contributions list is empty when the heuristic path served.
    """
    features = extract_features(student)
    model = _load_model()
    if model is not None:
        ml_score = _model_score(model, features)
        if ml_score is not None:
            score = max(0.0, min(100.0, ml_score))
            contributions = explain_score(model, features)
            if contributions:
                reason = _format_contribution_reason(contributions)
            else:
                reason = _heuristic_score(features)[1]
            model_version = (
                getattr(model, "model_version", None)
                or os.path.basename(_model_path())
                or "ml-v1"
            )
            return round(score, 2), reason, str(model_version), contributions
    score, reason = _heuristic_score(features)
    return score, reason, None, []
