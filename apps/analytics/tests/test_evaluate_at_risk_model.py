"""Tests for the `evaluate_at_risk_model` mgmt command.

Train a small synthetic model in-test, then evaluate it via the command.
Skips when sklearn/joblib aren't installed (matches train_at_risk.py's
soft-fail contract).
"""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from io import StringIO

from django.core.management import CommandError, call_command
from django.test import SimpleTestCase

try:
    import joblib  # noqa: F401
    import sklearn  # noqa: F401
    _HAS_SKLEARN = True
except ImportError:
    _HAS_SKLEARN = False


@unittest.skipUnless(_HAS_SKLEARN, "sklearn/joblib not installed")
class EvaluateAtRiskModelTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        import joblib
        from sklearn.ensemble import GradientBoostingClassifier

        from apps.analytics.ml.synthetic_at_risk_dataset import (
            FEATURE_ORDER,
            generate,
        )

        cls._tmpdir = tempfile.TemporaryDirectory()
        cls.artifact_path = os.path.join(cls._tmpdir.name, "model.joblib")

        X, y = generate(n_samples=400, seed=7)
        clf = GradientBoostingClassifier(
            n_estimators=30, max_depth=2, learning_rate=0.1, random_state=7
        )
        clf.fit(X, y)
        joblib.dump(
            {
                "model": clf,
                "feature_order": list(FEATURE_ORDER),
                "model_version": "test_v1",
            },
            cls.artifact_path,
        )

    @classmethod
    def tearDownClass(cls):
        cls._tmpdir.cleanup()
        super().tearDownClass()

    def test_reports_metrics_on_synthetic_holdout(self):
        out = StringIO()
        call_command(
            "evaluate_at_risk_model",
            self.artifact_path,
            "--samples", "200",
            "--seed", "999",
            stdout=out,
        )
        text = out.getvalue()
        self.assertIn("roc_auc", text)
        self.assertIn("average_precision", text)
        self.assertIn("precision_at_threshold", text)

    def test_writes_json_report(self):
        report_path = os.path.join(self._tmpdir.name, "report.json")
        call_command(
            "evaluate_at_risk_model",
            self.artifact_path,
            "--samples", "200",
            "--seed", "999",
            "--json", report_path,
            stdout=StringIO(),
        )
        data = json.loads(open(report_path).read())
        self.assertEqual(data["model_version"], "test_v1")
        self.assertEqual(data["holdout_size"], 200)
        self.assertIn("roc_auc", data["metrics"])
        self.assertIn("confusion_matrix", data)
        cm = data["confusion_matrix"]
        self.assertEqual(set(cm.keys()), {"tn", "fp", "fn", "tp"})

    def test_deploy_gate_fails_when_threshold_unmet(self):
        with self.assertRaises(CommandError) as ctx:
            call_command(
                "evaluate_at_risk_model",
                self.artifact_path,
                "--samples", "200",
                "--seed", "999",
                "--min-roc-auc", "0.999",
                stdout=StringIO(),
            )
        self.assertIn("deploy gate", str(ctx.exception))

    def test_missing_artifact_raises(self):
        with self.assertRaises(CommandError):
            call_command(
                "evaluate_at_risk_model",
                "/no/such/path.joblib",
                stdout=StringIO(),
            )
