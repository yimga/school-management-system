"""Wave 3 tests — per-prediction explainability.

Exercises `explain_score` against tree-style fake models (with
`feature_importances_`), linear-style (with `coef_`), and unsupported
estimators (neither attribute). All pure-Python; no DB required.
"""

from __future__ import annotations

from django.test import SimpleTestCase

from apps.analytics.ml.at_risk_features import AtRiskFeatures
from apps.analytics.ml.at_risk_model import (
    _FEATURE_NAMES,
    _format_contribution_reason,
    explain_score,
)


class _FakeTreeModel:
    """Stand-in sklearn tree model exposing feature_importances_."""

    def __init__(self, importances):
        self.feature_importances_ = importances


class _FakeLinearModel:
    """Stand-in sklearn linear model exposing coef_."""

    def __init__(self, coef):
        self.coef_ = [coef]  # binary classifier shape: [[w0, w1, ...]]


class _NaiveModel:
    """No attribute the explainer can use."""


class ExplainScoreTests(SimpleTestCase):
    def _features(self, **overrides):
        f = AtRiskFeatures(student_id="x")
        for k, v in overrides.items():
            setattr(f, k, v)
        return f

    def test_tree_model_returns_top_k_in_importance_order(self):
        # 9 features; attendance_rate gets the highest importance.
        importances = [0.40, 0.05, 0.05, 0.20, 0.05, 0.10, 0.05, 0.05, 0.05]
        model = _FakeTreeModel(importances)
        features = self._features(
            attendance_rate=0.60, avg_evaluation_score=50.0,
            eval_score_trend=-10.0,
        )
        out = explain_score(model, features, top_k=3)
        self.assertEqual(len(out), 3)
        names = [c["name"] for c in out]
        # The top importance is attendance_rate (0.40), then
        # avg_evaluation_score (0.20), then eval_score_trend (0.10).
        self.assertEqual(names[0], "attendance_rate")
        self.assertEqual(names[1], "avg_evaluation_score")
        self.assertEqual(names[2], "eval_score_trend")

    def test_direction_tag_respects_inverse_features(self):
        importances = [0.50, 0.05, 0.05, 0.05, 0.05, 0.05, 0.05, 0.05, 0.15]
        model = _FakeTreeModel(importances)
        # Low attendance_rate vs baseline 0.95 → "elevates" (inverse direction).
        features = self._features(attendance_rate=0.50, days_since_last_login=2)
        out = explain_score(model, features, top_k=2)
        attendance = next(c for c in out if c["name"] == "attendance_rate")
        self.assertEqual(attendance["direction"], "elevates")
        # High days_since_last_login=14 vs baseline 7 → "elevates" (direct).
        # But here we set 2 days < baseline 7 → "lowers".
        login = next(c for c in out if c["name"] == "days_since_last_login")
        self.assertEqual(login["direction"], "lowers")

    def test_high_attendance_lowers_risk(self):
        importances = [0.99] + [0.001 / 8] * 8
        # Normalise to sum=1 isn't required; just need attendance to dominate.
        model = _FakeTreeModel(importances)
        features = self._features(attendance_rate=0.99)
        top = explain_score(model, features, top_k=1)[0]
        self.assertEqual(top["name"], "attendance_rate")
        self.assertEqual(top["direction"], "lowers")

    def test_linear_model_uses_abs_coef(self):
        coef = [-0.8, 0.1, 0.05, -0.3, 0.0, 0.0, 0.0, 0.0, 0.0]
        model = _FakeLinearModel(coef)
        features = self._features(
            attendance_rate=0.50, avg_evaluation_score=40.0,
        )
        out = explain_score(model, features, top_k=2)
        self.assertEqual(out[0]["name"], "attendance_rate")
        self.assertEqual(out[1]["name"], "avg_evaluation_score")

    def test_unsupported_estimator_returns_empty(self):
        self.assertEqual(explain_score(_NaiveModel(), self._features()), [])

    def test_mismatched_feature_count_returns_empty(self):
        # 8 importances vs 9 features → mismatched, returns [].
        model = _FakeTreeModel([0.5, 0.1, 0.1, 0.1, 0.05, 0.05, 0.05, 0.05])
        self.assertEqual(explain_score(model, self._features()), [])

    def test_format_contribution_reason(self):
        contributions = [
            {"name": "attendance_rate", "value": 0.62,
             "importance": 0.31, "direction": "elevates"},
            {"name": "avg_evaluation_score", "value": 54.0,
             "importance": 0.22, "direction": "elevates"},
        ]
        text = _format_contribution_reason(contributions)
        self.assertIn("Top model drivers", text)
        self.assertIn("attendance_rate=0.62", text)
        self.assertIn("31%", text)
        self.assertTrue(text.endswith("."))

    def test_empty_contributions_yields_empty_string(self):
        self.assertEqual(_format_contribution_reason([]), "")

    def test_feature_names_constant_matches_features_vector(self):
        # Guardrail: as_vector() ordering must match _FEATURE_NAMES.
        feats = AtRiskFeatures(student_id="x")
        self.assertEqual(len(feats.as_vector()), len(_FEATURE_NAMES))
