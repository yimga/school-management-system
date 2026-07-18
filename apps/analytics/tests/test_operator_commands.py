"""Tests for operator-facing helper commands shipped after Wave 10:
bootstrap_at_risk_registry, verify_ai_ml_readiness, Celery task wrappers.
"""

from __future__ import annotations

import os
import tempfile
import unittest.mock as mock
from io import StringIO

from django.core.management import call_command
from django.test import TestCase, override_settings

from apps.accounts.models import User
from apps.analytics.models import AtRiskModelArtifact


class BootstrapRegistryTests(TestCase):
    def _make_artifact(self):
        tmp = tempfile.NamedTemporaryFile(suffix=".joblib", delete=False)
        tmp.write(b"placeholder bundle")
        tmp.close()
        return tmp.name

    def setUp(self):
        self.path = self._make_artifact()
        self.op = User.objects.create_user(
            username=f"boot_{id(self)}",
            email="o@example.com", password="p",
        )

    def tearDown(self):
        os.unlink(self.path)

    def test_registers_and_promotes(self):
        call_command(
            "bootstrap_at_risk_registry",
            "--artifact", self.path,
            "--operator-username", self.op.username,
            stdout=StringIO(),
        )
        # Default version is `legacy_<basename>_<sha8>` — single row exists.
        rows = AtRiskModelArtifact.objects.all()
        self.assertEqual(rows.count(), 1)
        self.assertEqual(
            rows.first().status, AtRiskModelArtifact.Status.PRODUCTION,
        )

    def test_idempotent_rerun(self):
        call_command(
            "bootstrap_at_risk_registry",
            "--artifact", self.path,
            "--model-version", "boot_v1",
            "--operator-username", self.op.username,
            stdout=StringIO(),
        )
        out = StringIO()
        call_command(
            "bootstrap_at_risk_registry",
            "--artifact", self.path,
            "--model-version", "boot_v1",
            "--operator-username", self.op.username,
            stdout=out,
        )
        self.assertIn("already exists", out.getvalue())
        # Still exactly one row, still PRODUCTION.
        self.assertEqual(AtRiskModelArtifact.objects.count(), 1)

    def test_no_promote_flag(self):
        call_command(
            "bootstrap_at_risk_registry",
            "--artifact", self.path,
            "--model-version", "boot_no_promote",
            "--operator-username", self.op.username,
            "--no-promote",
            stdout=StringIO(),
        )
        row = AtRiskModelArtifact.objects.get(model_version="boot_no_promote")
        self.assertEqual(row.status, AtRiskModelArtifact.Status.CANDIDATE)

    def test_skips_missing_artifact(self):
        out = StringIO()
        call_command(
            "bootstrap_at_risk_registry",
            "--artifact", "/no/such/path.joblib",
            "--operator-username", self.op.username,
            stdout=out,
        )
        self.assertIn("does not exist", out.getvalue())
        self.assertEqual(AtRiskModelArtifact.objects.count(), 0)

    def test_skips_unknown_operator(self):
        out = StringIO()
        call_command(
            "bootstrap_at_risk_registry",
            "--artifact", self.path,
            "--operator-username", "nope_does_not_exist",
            stdout=out,
        )
        self.assertIn("No operator user available", out.getvalue())
        self.assertEqual(AtRiskModelArtifact.objects.count(), 0)


class VerifyAiMlReadinessTests(TestCase):
    def test_human_readable_output(self):
        out = StringIO()
        call_command("verify_ai_ml_readiness", stdout=out)
        text = out.getvalue()
        self.assertIn("AI/ML readiness:", text)
        # Each of the 9 checks must appear.
        for key in (
            "schema", "registry", "production", "inference_recency",
            "embeddings", "digest_recipients",
            "shap_optional", "pgvector_optional", "celery_beat",
        ):
            self.assertIn(key, text)

    def test_json_output(self):
        import json
        out = StringIO()
        call_command("verify_ai_ml_readiness", "--json", stdout=out)
        payload = json.loads(out.getvalue())
        self.assertEqual(len(payload), 9)
        names = {r["check"] for r in payload}
        self.assertIn("schema", names)
        self.assertIn("celery_beat", names)

    def test_strict_exits_when_required_failing(self):
        # In the fresh test DB nothing is registered → registry check fails.
        with self.assertRaises(SystemExit) as ctx:
            call_command(
                "verify_ai_ml_readiness", "--strict", stdout=StringIO(),
            )
        self.assertEqual(ctx.exception.code, 1)

    @override_settings(CELERY_BEAT_SCHEDULE={
        "analytics-compute-nightly-risk": {
            "task": "analytics.compute_nightly_risk", "schedule": 86400.0,
        },
    })
    def test_celery_beat_check_passes_when_entry_present(self):
        import json
        out = StringIO()
        call_command("verify_ai_ml_readiness", "--json", stdout=out)
        payload = json.loads(out.getvalue())
        celery_row = next(r for r in payload if r["check"] == "celery_beat")
        self.assertTrue(celery_row["ok"])


class CeleryTaskWrappersTests(TestCase):
    """Confirm the wrapper functions exist and call the underlying mgmt commands."""

    def test_wrappers_exist(self):
        from apps.analytics import celery_tasks
        for attr in (
            "compute_nightly_risk_task",
            "compute_nightly_grade_predictions_task",
            "build_student_embeddings_task",
            "check_at_risk_drift_watchdog",
        ):
            self.assertTrue(
                hasattr(celery_tasks, attr),
                f"celery_tasks.{attr} missing",
            )
        # send_risk_digest_task now lives in its own module so autodiscovery
        # (which re-exports the four safe wrappers from celery_tasks via tasks.py)
        # cannot wake the outbound-email/LLM risk-digest task as a side effect.
        # See apps/analytics/celery_tasks_risk_digest.py + verify_beat_task_registry
        # KNOWN_DEAD_ENTRIES.
        from apps.analytics import celery_tasks_risk_digest
        self.assertTrue(
            hasattr(celery_tasks_risk_digest, "send_risk_digest_task"),
            "celery_tasks_risk_digest.send_risk_digest_task missing",
        )

    def test_safe_call_swallows_exception(self):
        from apps.analytics.celery_tasks import _safe_call
        with mock.patch(
            "apps.analytics.celery_tasks.call_command",
            side_effect=RuntimeError("boom"),
        ):
            out = _safe_call("compute_nightly_risk")
        # Should not raise; returns whatever stdout captured (empty).
        self.assertIsInstance(out, str)

    def test_safe_call_handles_systemexit(self):
        from apps.analytics.celery_tasks import _safe_call
        with mock.patch(
            "apps.analytics.celery_tasks.call_command",
            side_effect=SystemExit(10),
        ):
            out = _safe_call("should_retrain_at_risk")
        self.assertIsInstance(out, str)
