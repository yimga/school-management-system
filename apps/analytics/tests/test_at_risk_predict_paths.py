"""Wave H (2026-05-15): predict_at_risk path tests.

Verifies that the predictor:
* falls back to the heuristic when no ML artifact is configured;
* loads + uses the ML artifact when ``AT_RISK_MODEL_PATH`` points at one;
* gracefully returns to the heuristic when the artifact fails to load;
* the joblib cache reload mechanism works.

Uses ``unittest.mock`` to inject a synthetic predictor — does not require
scikit-learn or joblib at test time.
"""

from __future__ import annotations

from io import StringIO
from unittest import mock

from django.core.management import call_command
from django.test import TestCase, override_settings

from apps.analytics.ml.at_risk_features import AtRiskFeatures
from apps.analytics.ml import at_risk_model as arm
from apps.analytics.ml.at_risk_model import predict_at_risk


def _stub_features(_student):
    """Stable feature vector — avoids touching the real student data path."""
    return AtRiskFeatures(
        student_id="stub-student",
        attendance_rate=0.70,            # below threshold → drives heuristic up
        absence_count=10,
        late_count=2,
        avg_evaluation_score=55.0,       # below 60 → adds risk
        evaluation_count=8,
        eval_score_trend=-8.0,           # negative trend → adds risk
        open_invoice_count=1,
        open_balance_amount=200.0,
        days_since_last_login=45,        # > 30 → adds risk
    )


class _FakeStudent:
    pk = "stub-student"


class HeuristicPathTests(TestCase):
    databases = {"default"}

    def setUp(self):
        arm._MODEL_CACHE.clear()

    @override_settings(AT_RISK_MODEL_PATH="")
    def test_heuristic_used_when_no_artifact_path(self):
        with mock.patch("apps.analytics.ml.at_risk_model.extract_features", _stub_features):
            score, reason, model_version = predict_at_risk(_FakeStudent())
        self.assertGreater(score, 0)
        self.assertIn("attendance", reason)
        self.assertIsNone(model_version)

    @override_settings(AT_RISK_MODEL_PATH="/nonexistent/path/to/model.joblib")
    def test_failed_artifact_load_falls_back_to_heuristic(self):
        with mock.patch("apps.analytics.ml.at_risk_model.extract_features", _stub_features):
            score, reason, model_version = predict_at_risk(_FakeStudent())
        self.assertGreater(score, 0)
        self.assertIsNone(model_version)


class _FakeMLModel:
    """Predicts a fixed score that beats the heuristic's signal."""
    model_version = "fake-classifier@1.0.0"

    def predict_proba(self, _X):
        return [[0.05, 0.95]]  # P(at_risk=True) = 95%


class ArtifactPathTests(TestCase):
    databases = {"default"}

    def setUp(self):
        arm._MODEL_CACHE.clear()

    @override_settings(AT_RISK_MODEL_PATH="/fake/artifact.joblib")
    def test_artifact_used_when_loaded(self):
        with mock.patch("joblib.load", return_value=_FakeMLModel()), \
             mock.patch("apps.analytics.ml.at_risk_model.extract_features", _stub_features):
            score, _reason, model_version = predict_at_risk(_FakeStudent())
        self.assertAlmostEqual(score, 95.0, delta=0.5)
        self.assertEqual(model_version, "fake-classifier@1.0.0")

    @override_settings(AT_RISK_MODEL_PATH="/fake/artifact.joblib")
    def test_model_score_clamped_to_0_100(self):
        class OverScoring:
            model_version = "v1"
            def predict_proba(self, _X):
                return [[0.0, 5.0]]  # would be 500 if not clamped

        with mock.patch("joblib.load", return_value=OverScoring()), \
             mock.patch("apps.analytics.ml.at_risk_model.extract_features", _stub_features):
            score, _reason, _model_version = predict_at_risk(_FakeStudent())
        self.assertLessEqual(score, 100.0)
        self.assertGreaterEqual(score, 0.0)

    @override_settings(AT_RISK_MODEL_PATH="/fake/artifact.joblib")
    def test_artifact_predict_failure_falls_back_to_heuristic(self):
        class Broken:
            model_version = "v1"
            def predict_proba(self, _X):
                raise RuntimeError("boom")

        with mock.patch("joblib.load", return_value=Broken()), \
             mock.patch("apps.analytics.ml.at_risk_model.extract_features", _stub_features):
            score, reason, model_version = predict_at_risk(_FakeStudent())
        self.assertGreater(score, 0)
        self.assertIsNone(model_version)
        self.assertIn("attendance", reason)


class ScoreStudentRiskCommandTests(TestCase):
    databases = {"default"}

    def test_command_errors_without_target(self):
        out = StringIO()
        err = StringIO()
        call_command("score_student_risk", stdout=out, stderr=err)
        self.assertIn("--student", err.getvalue())

    def test_reload_clears_model_cache(self):
        arm._MODEL_CACHE["model"] = "sentinel"
        # No --student / --school: it errors after clearing the cache.
        call_command("score_student_risk", "--reload", stdout=StringIO(), stderr=StringIO())
        self.assertNotIn("model", arm._MODEL_CACHE)
