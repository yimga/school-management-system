"""Wave O1 — at-risk ML artifact readiness preflight.

Sister module to ``apps/schools/residency_readiness.py`` (K4) and
``apps/security/csp_readiness.py`` (L2). Asserts that the at-risk
predictor will fire the ML inference path (not silently fall back to
heuristic) at request time.

Three states the predictor can be in:

1. **Artifact path unset and no auto-discovery** → heuristic-only mode.
   This is the default zero-config state; it produces predictions but
   the platform isn't getting ML-grade signal.
2. **Path set but artifact missing / unloadable / wrong shape** →
   heuristic-fallback mode. This is the dangerous state: ops thinks
   ML is on; the predictor logs a warning and falls back. Without this
   preflight, nobody notices until someone audits the
   `model_version` column of `RiskFactor`.
3. **Path set, artifact loads, bundle shape valid** → ml-artifact path
   fires. The preflight reports ready=True only in this state.

Checks performed:

* **Path resolution** — ``settings.AT_RISK_MODEL_PATH`` (explicit) or
  the auto-discovery default (``AT_RISK_MODEL_DIR/at_risk_v1.joblib``)
  resolves to a non-blank string.
* **File present** — the resolved path exists on disk.
* **File loadable** — ``joblib.load(path)`` succeeds.
* **Bundle shape** — when the artifact is a dict bundle (the canonical
  shape produced by ``train_at_risk.py``), it has the expected keys
  (``model``, ``feature_order``, ``model_version``) and the model
  exposes ``predict_proba`` or ``predict``.
* **Heuristic-only mode is acceptable** — when no path is set at all,
  the preflight reports ``mode=heuristic`` and ready=True. The platform
  isn't broken; it just isn't using ML. Operators flipping the artifact
  toggle are the ones who care about ml-mode readiness.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from django.conf import settings


@dataclass
class AtRiskReadinessReport:
    """Outcome of the at-risk preflight."""

    ready: bool = True
    mode: str = "heuristic"
    """One of: 'heuristic' (no path set), 'ml-artifact' (loadable + valid),
    'misconfigured' (path set but artifact fails to load / wrong shape)."""

    resolved_path: str = ""
    """The path the predictor would load (from settings or auto-discovery)."""

    artifact_exists: bool = False
    artifact_loadable: bool = False
    bundle_shape_valid: bool = False
    bundle_model_version: str = ""
    """Populated when the artifact is a dict bundle with ``model_version``."""

    error_detail: str = ""
    """Free-text diagnostic when ``ready`` is False (load error, missing
    keys, etc.)."""

    def issue_count(self) -> int:
        # ml-artifact mode requires all three checks pass. Heuristic mode
        # is intentionally "ready=True with 0 issues" because the platform
        # isn't broken — it's just not using ML.
        if self.mode == "heuristic":
            return 0
        return (
            (0 if self.artifact_exists else 1)
            + (0 if self.artifact_loadable else 1)
            + (0 if self.bundle_shape_valid else 1)
        )


def _resolve_path() -> str:
    """Return the path the predictor would load.

    Mirrors `apps/analytics/ml/at_risk_model._model_path` resolution:
    settings.AT_RISK_MODEL_PATH wins; env AT_RISK_MODEL_PATH falls back.
    Also honours the Wave K3 auto-discovery from AT_RISK_MODEL_DIR.
    """
    explicit = (
        getattr(settings, "AT_RISK_MODEL_PATH", "") or ""
    ).strip()
    if explicit:
        return explicit
    env = (os.environ.get("AT_RISK_MODEL_PATH") or "").strip()
    if env:
        return env
    auto_dir = getattr(settings, "AT_RISK_MODEL_DIR", "")
    if auto_dir:
        candidate = os.path.join(auto_dir, "at_risk_v1.joblib")
        if os.path.exists(candidate):
            return candidate
    return ""


def assess_at_risk_readiness() -> AtRiskReadinessReport:
    """Run the full at-risk preflight; never raises.

    Returns mode='heuristic' + ready=True when no path is configured,
    so a fresh install passes this preflight by default. Operators only
    fail this when they've explicitly opted into ML mode and something
    is wrong with the artifact.
    """
    report = AtRiskReadinessReport()
    report.resolved_path = _resolve_path()

    if not report.resolved_path:
        # No artifact configured anywhere — heuristic-only mode.
        report.mode = "heuristic"
        report.ready = True
        return report

    report.artifact_exists = os.path.exists(report.resolved_path)
    if not report.artifact_exists:
        report.mode = "misconfigured"
        report.ready = False
        report.error_detail = f"file not found at {report.resolved_path}"
        return report

    try:
        import joblib  # type: ignore

        loaded = joblib.load(report.resolved_path)
    except (ImportError, FileNotFoundError, OSError, ValueError) as exc:
        report.mode = "misconfigured"
        report.ready = False
        report.artifact_loadable = False
        report.error_detail = f"joblib.load failed: {exc}"
        return report

    report.artifact_loadable = True

    # Bundle shape check. The canonical dict shape from train_at_risk.py
    # has keys {model, feature_order, model_version, training}. We accept
    # raw classifier objects too (legacy artifacts) — they must expose
    # predict_proba / predict.
    estimator = loaded
    if isinstance(loaded, dict):
        if "model" not in loaded:
            report.mode = "misconfigured"
            report.ready = False
            report.error_detail = "bundle dict missing 'model' key"
            return report
        estimator = loaded["model"]
        version = loaded.get("model_version")
        if isinstance(version, str) and version:
            report.bundle_model_version = version
        # 'feature_order' is informational; missing is non-fatal but worth
        # noting so the predictor has a stable feature schema.
        if "feature_order" not in loaded:
            report.error_detail = "bundle missing 'feature_order' key (non-fatal)"

    if not (hasattr(estimator, "predict_proba") or hasattr(estimator, "predict")):
        report.mode = "misconfigured"
        report.ready = False
        report.bundle_shape_valid = False
        report.error_detail = (
            "loaded model has neither predict_proba nor predict — "
            "incompatible with apps.analytics.ml.at_risk_model._model_score"
        )
        return report

    report.bundle_shape_valid = True
    report.mode = "ml-artifact"
    report.ready = True
    return report


__all__ = ["AtRiskReadinessReport", "assess_at_risk_readiness"]
