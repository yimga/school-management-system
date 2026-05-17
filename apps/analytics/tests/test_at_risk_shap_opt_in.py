"""Wave 10 tests — SHAP-based explainer opt-in.

The `shap` library is intentionally NOT a hard dependency. Tests
either monkey-patch a fake `shap` module into sys.modules or assert
the soft fall-through to the fast path when it's missing.
"""

from __future__ import annotations

import sys
import types
import unittest.mock as mock

from django.test import SimpleTestCase

from apps.analytics.ml.at_risk_features import AtRiskFeatures
from apps.analytics.ml.at_risk_model import _FEATURE_NAMES, explain_score


class _FakeTreeModel:
    def __init__(self, importances):
        self.feature_importances_ = importances


class ShapFallthroughTests(SimpleTestCase):
    def test_method_shap_falls_through_when_lib_missing(self):
        # If `shap` truly isn't installed in test env, method="shap"
        # should silently degrade to the fast path. Confirm by asserting
        # we still get the fast-path shape (no shap_value key).
        with mock.patch.dict(sys.modules, {"shap": None}):
            model = _FakeTreeModel([0.4, 0.05, 0.05, 0.2, 0.05, 0.1, 0.05, 0.05, 0.05])
            features = AtRiskFeatures(student_id="x", attendance_rate=0.5)
            out = explain_score(model, features, method="shap", top_k=2)
        self.assertEqual(len(out), 2)
        # Fast path doesn't include shap_value.
        for item in out:
            self.assertNotIn("shap_value", item)


class ShapHappyPathTests(SimpleTestCase):
    """Stub `shap.TreeExplainer` and assert SHAP values flow through."""

    def setUp(self):
        # Build a fake `shap` module exposing TreeExplainer + shap_values.
        fake_module = types.ModuleType("shap")

        class _FakeExplainer:
            def __init__(self, model):
                self.model = model

            def shap_values(self, X):
                # Binary classifier return shape: list of 2 ndarrays.
                # Positive-class array shape: (1, n_features).
                # Provide a clearly-ordered signal so importance ranking is testable.
                _row = X[0]
                # SHAP values: bigger magnitude → more important.
                # Negative for attendance_rate (lowers risk per high value),
                # positive for everything else.
                return [
                    [[0.0] * len(_row)],   # negative class
                    [[
                        -0.5,  # attendance_rate (lowers)
                        0.1,
                        0.05,
                        0.3,   # avg_evaluation_score
                        0.05,
                        0.05,
                        0.05,
                        0.05,
                        0.05,
                    ]],
                ]

        fake_module.TreeExplainer = _FakeExplainer
        self._patch = mock.patch.dict(sys.modules, {"shap": fake_module})
        self._patch.start()

    def tearDown(self):
        self._patch.stop()

    def test_shap_values_ordered_by_abs_magnitude(self):
        model = _FakeTreeModel([0.0] * 9)  # importances irrelevant on shap path
        features = AtRiskFeatures(student_id="x", attendance_rate=0.92)
        out = explain_score(model, features, method="shap", top_k=3)
        self.assertEqual(len(out), 3)
        # Top should be attendance_rate (|−0.5|=0.5).
        self.assertEqual(out[0]["name"], "attendance_rate")
        self.assertEqual(out[0]["direction"], "lowers")
        # Second should be avg_evaluation_score (|0.3|=0.3, elevates).
        self.assertEqual(out[1]["name"], "avg_evaluation_score")
        self.assertEqual(out[1]["direction"], "elevates")

    def test_shap_value_field_present(self):
        model = _FakeTreeModel([0.0] * 9)
        features = AtRiskFeatures(student_id="x")
        out = explain_score(model, features, method="shap", top_k=1)
        self.assertIn("shap_value", out[0])

    def test_default_method_does_not_invoke_shap(self):
        # method="fast" must NEVER touch the stub shap module.
        # We confirm by feeding a model whose feature_importances_ is
        # well-defined; the fast path returns those ranked importances.
        model = _FakeTreeModel(
            [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.9],  # last only
        )
        features = AtRiskFeatures(student_id="x")
        out = explain_score(model, features, top_k=1)  # default method
        self.assertEqual(out[0]["name"], _FEATURE_NAMES[-1])
        # Fast path: no shap_value key.
        self.assertNotIn("shap_value", out[0])


class ShapShapeMismatchTests(SimpleTestCase):
    """If the stub returns the wrong shape, gracefully fall back."""

    def test_mismatched_shap_vec_returns_empty_shap_then_fast(self):
        fake_module = types.ModuleType("shap")

        class _BadExplainer:
            def __init__(self, model): pass
            def shap_values(self, X):
                return [[1.0, 2.0]]  # only 2 entries vs 9 features

        fake_module.TreeExplainer = _BadExplainer
        with mock.patch.dict(sys.modules, {"shap": fake_module}):
            model = _FakeTreeModel([0.5] + [0.0] * 8)
            features = AtRiskFeatures(student_id="x")
            out = explain_score(model, features, method="shap", top_k=2)
        # SHAP returned mismatched shape → empty → fast-path attempts.
        # Fast path's first item should be attendance_rate (importance 0.5).
        self.assertEqual(out[0]["name"], "attendance_rate")
        self.assertNotIn("shap_value", out[0])
