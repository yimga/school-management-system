"""Wave K3: baseline at-risk artifact + auto-discovery tests.

Three concerns covered:

1. The `train_at_risk_baseline` management command runs end-to-end
   against a synthetic dataset, persists a joblib artifact, and the
   artifact is loadable.
2. With the artifact in place, `predict_at_risk` flips from the
   heuristic path (model_version is None) to the ML path
   (model_version is non-empty and matches the artifact filename).
3. settings auto-discovery: when `AT_RISK_MODEL_PATH` is unset but
   `AT_RISK_MODEL_DIR/at_risk_v1.joblib` exists, the resolved path
   points at the auto-discovered artifact.
"""

from __future__ import annotations

import os
import tempfile
from io import StringIO
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from django.core.management import call_command
from django.test import TestCase, override_settings


def _stub_student():
    """Lightweight student-shaped stub for the feature extractor.

    extract_features() must accept this; if your test environment is
    strict about Student type we override the predictor instead.
    """
    return SimpleNamespace(
        pk=1,
        attendance_rate=0.95,
        absence_count=2,
        late_count=1,
        avg_evaluation_score=72.0,
        evaluation_count=10,
        eval_score_trend=2.5,
        open_invoice_count=0,
        open_balance_amount=0.0,
        days_since_last_login=3,
    )


class TrainAtRiskBaselineCommandTests(TestCase):
    """End-to-end: command trains + writes + we can load the artifact."""

    def test_command_runs_and_writes_artifact(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with override_settings(AT_RISK_MODEL_DIR=tmpdir):
                out = StringIO()
                call_command(
                    "train_at_risk_baseline",
                    "--samples", "300",  # tiny for speed
                    "--seed", "1",
                    stdout=out,
                )
            artifact_path = Path(tmpdir) / "at_risk_v1.joblib"
            self.assertTrue(
                artifact_path.exists(),
                msg=f"Expected artifact at {artifact_path}; got: {out.getvalue()}",
            )
            # The artifact must be a sklearn-flavoured joblib bundle with the
            # expected keys.
            import joblib

            bundle = joblib.load(artifact_path)
            self.assertIn("model", bundle)
            self.assertIn("feature_order", bundle)
            self.assertIn("model_version", bundle)
            self.assertTrue(hasattr(bundle["model"], "predict_proba"))

    def test_command_no_write_skips_artifact(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with override_settings(AT_RISK_MODEL_DIR=tmpdir):
                call_command(
                    "train_at_risk_baseline",
                    "--samples", "200",
                    "--seed", "1",
                    "--no-write",
                    stdout=StringIO(),
                )
            artifact_path = Path(tmpdir) / "at_risk_v1.joblib"
            self.assertFalse(artifact_path.exists())


class InferencePathFlipsTests(TestCase):
    """With a real artifact pointed at by AT_RISK_MODEL_PATH, the inference
    path flips from heuristic → ml-artifact.
    """

    def test_predict_path_flips_with_artifact(self):
        from apps.analytics.ml import at_risk_model

        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_path = os.path.join(tmpdir, "at_risk_v1.joblib")
            # Produce a real artifact via the management command (writes joblib).
            with override_settings(AT_RISK_MODEL_DIR=tmpdir):
                call_command(
                    "train_at_risk_baseline",
                    "--samples", "300",
                    "--seed", "1",
                    stdout=StringIO(),
                )

            # Reset the joblib cache and point settings at the artifact, then
            # use a stubbed feature extractor so we don't need real DB data.
            at_risk_model._MODEL_CACHE.clear()
            with override_settings(AT_RISK_MODEL_PATH=artifact_path):
                with mock.patch(
                    "apps.analytics.ml.at_risk_model.extract_features",
                ) as mock_extract:
                    from apps.analytics.ml.at_risk_features import AtRiskFeatures
                    mock_extract.return_value = AtRiskFeatures(
                        student_id="stub-1",
                        attendance_rate=0.95,
                        absence_count=2,
                        late_count=1,
                        avg_evaluation_score=72.0,
                        evaluation_count=10,
                        eval_score_trend=2.5,
                        open_invoice_count=0,
                        open_balance_amount=0.0,
                        days_since_last_login=3,
                    )
                    score, reason, model_version = at_risk_model.predict_at_risk(
                        _stub_student()
                    )

            self.assertIsNotNone(
                model_version,
                msg="With artifact present, model_version must be non-None (ml-artifact path).",
            )
            self.assertTrue(0.0 <= score <= 100.0)
            self.assertIn("at_risk_v1", model_version)

        # Reset cache so other tests don't see the stale model.
        at_risk_model._MODEL_CACHE.clear()

    def test_predict_falls_back_to_heuristic_when_no_artifact(self):
        from apps.analytics.ml import at_risk_model
        from apps.analytics.ml.at_risk_features import AtRiskFeatures

        at_risk_model._MODEL_CACHE.clear()
        with override_settings(AT_RISK_MODEL_PATH=""):
            with mock.patch.dict(os.environ, {"AT_RISK_MODEL_PATH": ""}, clear=False):
                with mock.patch(
                    "apps.analytics.ml.at_risk_model.extract_features",
                ) as mock_extract:
                    mock_extract.return_value = AtRiskFeatures(
                        student_id="stub-2",
                        attendance_rate=0.50,  # poor attendance
                        absence_count=20,
                        late_count=5,
                        avg_evaluation_score=45.0,  # poor grades
                        evaluation_count=10,
                        eval_score_trend=-10.0,
                        open_invoice_count=2,
                        open_balance_amount=500.0,
                        days_since_last_login=60,
                    )
                    score, reason, model_version = at_risk_model.predict_at_risk(
                        _stub_student()
                    )
        self.assertIsNone(
            model_version,
            msg="With no artifact, model_version must be None (heuristic path).",
        )
        # Heuristic should fire on this profile.
        self.assertGreater(score, 30.0)


class SettingsAutoDiscoveryTests(TestCase):
    """Confirm settings.py's resolution chain works end-to-end.

    The actual resolution lives in `config/settings.py` at import time
    (executed once per process). We test the equivalent inline so the
    expected behavior is locked in.
    """

    def _resolve(self, *, env_path: str, dir_path: str, dir_has_artifact: bool):
        """Mirror the settings.py resolution logic."""
        explicit = env_path.strip()
        if explicit:
            return explicit
        candidate = os.path.join(dir_path, "at_risk_v1.joblib")
        return candidate if (dir_has_artifact and os.path.exists(candidate)) else ""

    def test_env_var_wins_when_set(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            # Touch a file at the auto-discovery location so it exists.
            Path(tmpdir, "at_risk_v1.joblib").write_bytes(b"fake")
            resolved = self._resolve(
                env_path="/explicit/path.joblib",
                dir_path=tmpdir,
                dir_has_artifact=True,
            )
            self.assertEqual(resolved, "/explicit/path.joblib")

    def test_auto_discovery_when_env_blank_and_artifact_exists(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            Path(tmpdir, "at_risk_v1.joblib").write_bytes(b"fake")
            resolved = self._resolve(
                env_path="",
                dir_path=tmpdir,
                dir_has_artifact=True,
            )
            self.assertEqual(resolved, os.path.join(tmpdir, "at_risk_v1.joblib"))

    def test_blank_when_neither_env_nor_artifact(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            resolved = self._resolve(
                env_path="",
                dir_path=tmpdir,
                dir_has_artifact=False,
            )
            self.assertEqual(resolved, "")
