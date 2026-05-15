"""Wave O1: at-risk ML artifact readiness preflight tests."""

from __future__ import annotations

import os
import tempfile
from io import StringIO
from pathlib import Path
from unittest import mock

import joblib  # type: ignore

from django.core.management import call_command
from django.test import TestCase, override_settings

from apps.analytics.at_risk_readiness import assess_at_risk_readiness


def _valid_bundle_path(tmpdir: str) -> str:
    """Write a fake-but-valid bundle to disk; return path."""
    out = os.path.join(tmpdir, "at_risk_v1.joblib")

    class FakeEstimator:
        def predict_proba(self, X):
            return [[0.2, 0.8] for _ in X]

    joblib.dump(
        {
            "model": FakeEstimator(),
            "feature_order": ["a", "b"],
            "model_version": "at_risk_test_v1",
            "training": {"source": "test"},
        },
        out,
    )
    return out


class AtRiskReadinessTests(TestCase):
    """Mode classification covers heuristic / ml-artifact / misconfigured."""

    def test_no_path_set_is_heuristic_mode_ready(self):
        with override_settings(AT_RISK_MODEL_PATH="", AT_RISK_MODEL_DIR=""):
            with mock.patch.dict(os.environ, {"AT_RISK_MODEL_PATH": ""}, clear=False):
                report = assess_at_risk_readiness()
        self.assertEqual(report.mode, "heuristic")
        self.assertTrue(report.ready)
        self.assertEqual(report.issue_count(), 0)
        self.assertEqual(report.resolved_path, "")

    def test_path_set_to_missing_file_is_misconfigured(self):
        with override_settings(AT_RISK_MODEL_PATH="/no/such/path.joblib"):
            report = assess_at_risk_readiness()
        self.assertEqual(report.mode, "misconfigured")
        self.assertFalse(report.ready)
        self.assertFalse(report.artifact_exists)
        self.assertIn("not found", report.error_detail.lower())

    def test_valid_bundle_is_ml_artifact_mode(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = _valid_bundle_path(tmp)
            with override_settings(AT_RISK_MODEL_PATH=path):
                report = assess_at_risk_readiness()
        self.assertEqual(report.mode, "ml-artifact")
        self.assertTrue(report.ready)
        self.assertTrue(report.artifact_exists)
        self.assertTrue(report.artifact_loadable)
        self.assertTrue(report.bundle_shape_valid)
        self.assertEqual(report.bundle_model_version, "at_risk_test_v1")

    def test_bundle_without_model_key_is_misconfigured(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "bad.joblib")
            joblib.dump({"not_model": 42, "feature_order": ["a"]}, path)
            with override_settings(AT_RISK_MODEL_PATH=path):
                report = assess_at_risk_readiness()
        self.assertEqual(report.mode, "misconfigured")
        self.assertFalse(report.ready)
        self.assertIn("model", report.error_detail.lower())

    def test_bundle_with_incompatible_model_is_misconfigured(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "bad.joblib")
            joblib.dump({"model": "not-an-estimator-just-a-string"}, path)
            with override_settings(AT_RISK_MODEL_PATH=path):
                report = assess_at_risk_readiness()
        self.assertEqual(report.mode, "misconfigured")
        self.assertFalse(report.ready)
        self.assertIn("predict", report.error_detail.lower())

    def test_raw_classifier_artifact_is_ml_mode(self):
        """Legacy artifacts (raw classifier, not dict-wrapped) are accepted."""
        class FakeRaw:
            def predict(self, X):
                return [50.0 for _ in X]

        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "legacy.joblib")
            joblib.dump(FakeRaw(), path)
            with override_settings(AT_RISK_MODEL_PATH=path):
                report = assess_at_risk_readiness()
        self.assertEqual(report.mode, "ml-artifact")
        self.assertTrue(report.ready)

    def test_auto_discovery_finds_artifact_in_dir(self):
        """Wave K3 auto-discovery: AT_RISK_MODEL_DIR/at_risk_v1.joblib resolves."""
        with tempfile.TemporaryDirectory() as tmp:
            _valid_bundle_path(tmp)
            with override_settings(AT_RISK_MODEL_PATH="", AT_RISK_MODEL_DIR=tmp):
                with mock.patch.dict(os.environ, {"AT_RISK_MODEL_PATH": ""}, clear=False):
                    report = assess_at_risk_readiness()
        self.assertEqual(report.mode, "ml-artifact")
        self.assertTrue(report.ready)
        self.assertTrue(report.resolved_path.endswith("at_risk_v1.joblib"))

    def test_bundle_missing_feature_order_is_non_fatal(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "f.joblib")
            class E:
                def predict(self, X):
                    return [0 for _ in X]
            joblib.dump({"model": E(), "model_version": "v1"}, path)
            with override_settings(AT_RISK_MODEL_PATH=path):
                report = assess_at_risk_readiness()
        self.assertEqual(report.mode, "ml-artifact")
        self.assertTrue(report.ready)
        self.assertIn("feature_order", report.error_detail)


class VerifyAtRiskReadinessCommandTests(TestCase):
    def test_command_exits_0_in_heuristic_mode(self):
        with override_settings(AT_RISK_MODEL_PATH="", AT_RISK_MODEL_DIR=""):
            with mock.patch.dict(os.environ, {"AT_RISK_MODEL_PATH": ""}, clear=False):
                out = StringIO()
                call_command("verify_at_risk_readiness", stdout=out)
        self.assertIn("READY", out.getvalue())
        self.assertIn("heuristic", out.getvalue())

    def test_command_exits_1_when_misconfigured(self):
        with override_settings(AT_RISK_MODEL_PATH="/no/such/file.joblib"):
            with self.assertRaises(SystemExit) as cm:
                call_command(
                    "verify_at_risk_readiness", "--quiet", stdout=StringIO()
                )
            self.assertEqual(cm.exception.code, 1)


class OrchestratorAtRiskSectionTests(TestCase):
    """verify_platform_readiness should include the at_risk section."""

    def test_at_risk_section_runs_and_reports_mode(self):
        out = StringIO()
        with override_settings(AT_RISK_MODEL_PATH="", AT_RISK_MODEL_DIR=""):
            with mock.patch.dict(os.environ, {"AT_RISK_MODEL_PATH": ""}, clear=False):
                call_command(
                    "verify_platform_readiness",
                    "--section", "at_risk",
                    "--json",
                    stdout=out,
                )
        import json
        payload = json.loads(out.getvalue())
        self.assertIn("at_risk", payload["sections"])
        details = payload["sections"]["at_risk"]["details"]
        self.assertEqual(details["mode"], "heuristic")
