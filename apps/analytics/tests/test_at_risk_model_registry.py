"""Wave 1 tests — at-risk model registry, loader, register/promote commands.

Pure registry behavior (promote atomicity, current_production resolution),
loader precedence (registry > settings > env), and the register/promote
mgmt commands. The pipeline orchestrator is exercised at the unit-helper
level — its subprocess train step is intentionally not invoked.
"""

from __future__ import annotations

import os
import tempfile
from io import StringIO

from django.core.management import CommandError, call_command
from django.test import SimpleTestCase, TestCase, override_settings
from django.utils import timezone

from apps.accounts.models import User
from apps.analytics.models import AtRiskInferenceRun, AtRiskModelArtifact


class _MakeArtifactMixin:
    """Test helper — creates a registry row + its on-disk joblib stub.

    The joblib stub is a tiny placeholder; the loader bypass tests don't
    actually deserialise it (joblib.load is mocked away). Tests that
    need a real bundle skip when joblib isn't installed.
    """

    @classmethod
    def _make_user(cls, suffix: str) -> User:
        return User.objects.create_user(
            username=f"opr_{suffix}",
            email=f"opr_{suffix}@example.com",
            password="pwd",
        )

    @classmethod
    def _make_artifact(
        cls,
        operator: User,
        *,
        version: str,
        status: str = AtRiskModelArtifact.Status.CANDIDATE,
        roc_auc: float | None = 0.82,
        avg_precision: float | None = 0.55,
        ece: float | None = 0.08,
        path: str | None = None,
    ) -> AtRiskModelArtifact:
        # Default to a temp path so tests don't share state on disk.
        if path is None:
            tmp = tempfile.NamedTemporaryFile(
                suffix=".joblib", delete=False
            )
            tmp.write(b"placeholder")
            tmp.close()
            path = tmp.name
        promoted_at = (
            timezone.now() if status == AtRiskModelArtifact.Status.PRODUCTION else None
        )
        return AtRiskModelArtifact.objects.create(
            model_version=version,
            artifact_path=path,
            trained_at=timezone.now(),
            training_dataset_hash="abc",
            training_row_count=100,
            feature_order=["a", "b", "c"],
            metric_roc_auc=roc_auc,
            metric_average_precision=avg_precision,
            metric_ece=ece,
            status=status,
            registered_by=operator,
            promoted_at=promoted_at,
            promoted_by=operator if promoted_at else None,
        )


class RegistryAtomicityTests(_MakeArtifactMixin, TestCase):
    def test_promote_archives_previous_production(self):
        op = self._make_user("a")
        prev = self._make_artifact(
            op, version="v1", status=AtRiskModelArtifact.Status.PRODUCTION,
        )
        candidate = self._make_artifact(op, version="v2")
        archived = candidate.promote(by_user=op)
        prev.refresh_from_db()
        candidate.refresh_from_db()
        self.assertEqual(archived.pk, prev.pk)
        self.assertEqual(prev.status, AtRiskModelArtifact.Status.ARCHIVED)
        self.assertEqual(
            candidate.status, AtRiskModelArtifact.Status.PRODUCTION
        )
        self.assertIsNotNone(candidate.promoted_at)
        self.assertEqual(candidate.promoted_by_id, op.pk)

    def test_promote_when_no_previous_returns_none(self):
        op = self._make_user("b")
        candidate = self._make_artifact(op, version="v1")
        self.assertIsNone(candidate.promote(by_user=op))
        candidate.refresh_from_db()
        self.assertEqual(
            candidate.status, AtRiskModelArtifact.Status.PRODUCTION
        )

    def test_current_production_resolves_to_live_row(self):
        op = self._make_user("c")
        self._make_artifact(
            op, version="v1", status=AtRiskModelArtifact.Status.ARCHIVED,
        )
        live = self._make_artifact(
            op, version="v2", status=AtRiskModelArtifact.Status.PRODUCTION,
        )
        self._make_artifact(op, version="v3")  # candidate
        self.assertEqual(AtRiskModelArtifact.current_production().pk, live.pk)

    def test_current_production_returns_none_when_no_live_row(self):
        op = self._make_user("d")
        self._make_artifact(op, version="only_candidate")
        self.assertIsNone(AtRiskModelArtifact.current_production())


class LoaderPrecedenceTests(_MakeArtifactMixin, TestCase):
    """Loader resolves the path from registry first, then settings, then env."""

    def setUp(self):
        # Reset module cache so each test gets a clean lookup.
        from apps.analytics.ml import at_risk_model
        at_risk_model._MODEL_CACHE.clear()
        self._at_risk_model = at_risk_model

    def test_registry_path_wins_over_env(self):
        op = self._make_user("la")
        live = self._make_artifact(
            op, version="reg_live",
            status=AtRiskModelArtifact.Status.PRODUCTION,
        )
        with override_settings(AT_RISK_MODEL_PATH="/should/not/win.joblib"):
            self.assertEqual(self._at_risk_model._model_path(), live.artifact_path)

    def test_settings_wins_over_env_when_no_registry_row(self):
        self.assertIsNone(AtRiskModelArtifact.current_production())
        with override_settings(AT_RISK_MODEL_PATH="/from/settings.joblib"):
            os.environ["AT_RISK_MODEL_PATH"] = "/from/env.joblib"
            try:
                self.assertEqual(
                    self._at_risk_model._model_path(), "/from/settings.joblib"
                )
            finally:
                del os.environ["AT_RISK_MODEL_PATH"]

    def test_env_wins_when_neither_registry_nor_setting(self):
        self.assertIsNone(AtRiskModelArtifact.current_production())
        os.environ["AT_RISK_MODEL_PATH"] = "/from/env.joblib"
        try:
            with override_settings(AT_RISK_MODEL_PATH=None):
                self.assertEqual(self._at_risk_model._model_path(), "/from/env.joblib")
        finally:
            del os.environ["AT_RISK_MODEL_PATH"]

    def test_no_source_returns_empty_string(self):
        self.assertIsNone(AtRiskModelArtifact.current_production())
        with override_settings(AT_RISK_MODEL_PATH=None):
            os.environ.pop("AT_RISK_MODEL_PATH", None)
            self.assertEqual(self._at_risk_model._model_path(), "")


class RegisterCommandTests(_MakeArtifactMixin, TestCase):
    def test_register_creates_candidate(self):
        op = self._make_user("rc1")
        with tempfile.NamedTemporaryFile(suffix=".joblib", delete=False) as f:
            f.write(b"placeholder")
            artifact_path = f.name
        try:
            call_command(
                "register_at_risk_artifact",
                artifact_path,
                "--model-version", "test_register_v1",
                "--registered-by-username", op.username,
                "--notes", "test note",
                stdout=StringIO(),
            )
            row = AtRiskModelArtifact.objects.get(model_version="test_register_v1")
            self.assertEqual(row.status, AtRiskModelArtifact.Status.CANDIDATE)
            self.assertEqual(row.notes, "test note")
            self.assertEqual(row.registered_by_id, op.pk)
        finally:
            os.unlink(artifact_path)

    def test_duplicate_version_rejected(self):
        op = self._make_user("rc2")
        self._make_artifact(op, version="dup_v")
        with tempfile.NamedTemporaryFile(suffix=".joblib", delete=False) as f:
            artifact_path = f.name
        try:
            with self.assertRaises(CommandError) as ctx:
                call_command(
                    "register_at_risk_artifact",
                    artifact_path,
                    "--model-version", "dup_v",
                    "--registered-by-username", op.username,
                    stdout=StringIO(),
                )
            self.assertIn("already registered", str(ctx.exception))
        finally:
            os.unlink(artifact_path)

    def test_missing_artifact_path_rejected(self):
        op = self._make_user("rc3")
        with self.assertRaises(CommandError):
            call_command(
                "register_at_risk_artifact",
                "/no/such/path.joblib",
                "--model-version", "v_nopath",
                "--registered-by-username", op.username,
                stdout=StringIO(),
            )


class PromoteCommandTests(_MakeArtifactMixin, TestCase):
    def test_promote_basic_path(self):
        op = self._make_user("pa")
        a = self._make_artifact(op, version="prom_v1")
        call_command(
            "promote_at_risk_artifact",
            "prom_v1",
            "--promoted-by-username", op.username,
            stdout=StringIO(),
        )
        a.refresh_from_db()
        self.assertEqual(a.status, AtRiskModelArtifact.Status.PRODUCTION)

    def test_promote_fails_gate(self):
        op = self._make_user("pb")
        self._make_artifact(
            op, version="prom_low_auc", roc_auc=0.55,
        )
        with self.assertRaises(CommandError) as ctx:
            call_command(
                "promote_at_risk_artifact",
                "prom_low_auc",
                "--promoted-by-username", op.username,
                "--min-roc-auc", "0.70",
                stdout=StringIO(),
            )
        self.assertIn("Promotion gates failed", str(ctx.exception))

    def test_promote_rejected_requires_override(self):
        op = self._make_user("pc")
        self._make_artifact(
            op, version="prom_rejected",
            status=AtRiskModelArtifact.Status.REJECTED,
        )
        with self.assertRaises(CommandError) as ctx:
            call_command(
                "promote_at_risk_artifact",
                "prom_rejected",
                "--promoted-by-username", op.username,
                stdout=StringIO(),
            )
        self.assertIn("REJECTED", str(ctx.exception))


class InferenceRunModelTests(SimpleTestCase):
    """Smoke-check that the model __str__ and basic field defaults don't crash."""

    def test_choices_present(self):
        choices = dict(AtRiskInferenceRun.Outcome.choices)
        self.assertIn("ok", choices)
        self.assertIn("heuristic", choices)
        self.assertIn("partial", choices)
        self.assertIn("failed", choices)
