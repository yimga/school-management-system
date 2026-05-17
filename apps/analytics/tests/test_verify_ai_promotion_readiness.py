"""Tests for verify_ai_promotion_readiness.

The command's logic is in ``compute_readiness``, which is a pure
function over two model managers. We mock the model module rather than
seed the DB; the integration story is already covered by
``test_at_risk_shadow_scoring.py``.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable
from unittest import mock

from django.test import SimpleTestCase

from apps.analytics.management.commands.verify_ai_promotion_readiness import (
    compute_readiness,
)


@dataclass
class FakeArtifact:
    model_version: str


@dataclass
class FakeShadowRun:
    students_scored: int
    band_changes: int
    agreement_pct: float | None
    psi_score_distribution: float | None


class FakeQuerySet:
    def __init__(self, rows: Iterable):
        self._rows = list(rows)

    def filter(self, **kwargs):
        return self  # tests pre-shape the rows

    def order_by(self, *args, **kwargs):
        return self

    def first(self):
        return self._rows[0] if self._rows else None

    def __iter__(self):
        return iter(self._rows)


def _patched_models(
    *, production: FakeArtifact | None, candidate: FakeArtifact | None,
    shadow_runs: list[FakeShadowRun],
):
    """Build a fake models_ml_registry module suitable for mock.patch."""
    fake_artifact_cls = mock.MagicMock()
    fake_artifact_cls.current_production.return_value = production
    fake_artifact_cls.objects = FakeQuerySet([candidate] if candidate else [])

    class FakeStatus:
        CANDIDATE = "candidate"
    fake_artifact_cls.Status = FakeStatus

    fake_run_cls = mock.MagicMock()
    fake_run_cls.objects = FakeQuerySet(shadow_runs)

    class FakeOutcome:
        OK = "ok"
    fake_run_cls.Outcome = FakeOutcome

    return mock.patch.dict(
        "sys.modules",
        {
            "apps.analytics.models_ml_registry": mock.MagicMock(
                AtRiskModelArtifact=fake_artifact_cls,
                AtRiskShadowRun=fake_run_cls,
            )
        },
    )


class ComputeReadinessTests(SimpleTestCase):
    def test_no_candidate(self):
        with _patched_models(
            production=FakeArtifact("at_risk_v1"),
            candidate=None,
            shadow_runs=[],
        ):
            r = compute_readiness()
        self.assertEqual(r.verdict, "no-candidate")
        self.assertEqual(r.production_version, "at_risk_v1")
        self.assertIsNone(r.candidate_version)
        self.assertFalse(r.ready)

    def test_no_shadow_evidence(self):
        with _patched_models(
            production=FakeArtifact("at_risk_v1"),
            candidate=FakeArtifact("at_risk_v2"),
            shadow_runs=[],
        ):
            r = compute_readiness()
        self.assertEqual(r.verdict, "no-shadow-evidence")
        self.assertEqual(r.shadow_run_count, 0)
        self.assertFalse(r.ready)

    def test_insufficient_sample(self):
        runs = [
            FakeShadowRun(students_scored=10, band_changes=1, agreement_pct=0.95, psi_score_distribution=0.05),
        ]
        with _patched_models(
            production=FakeArtifact("v1"),
            candidate=FakeArtifact("v2"),
            shadow_runs=runs,
        ):
            r = compute_readiness(min_students=100)
        self.assertEqual(r.verdict, "insufficient-sample")
        self.assertEqual(r.students_scored, 10)
        self.assertFalse(r.ready)

    def test_failing_agreement(self):
        runs = [
            FakeShadowRun(students_scored=200, band_changes=50, agreement_pct=0.70, psi_score_distribution=0.05),
        ]
        with _patched_models(
            production=FakeArtifact("v1"),
            candidate=FakeArtifact("v2"),
            shadow_runs=runs,
        ):
            r = compute_readiness(min_students=100, min_agreement=0.85)
        self.assertEqual(r.verdict, "failing-agreement")
        self.assertAlmostEqual(r.agreement_pct, 0.70)
        self.assertFalse(r.ready)

    def test_failing_psi(self):
        runs = [
            FakeShadowRun(students_scored=200, band_changes=10, agreement_pct=0.95, psi_score_distribution=0.40),
        ]
        with _patched_models(
            production=FakeArtifact("v1"),
            candidate=FakeArtifact("v2"),
            shadow_runs=runs,
        ):
            r = compute_readiness(min_students=100, max_psi=0.25)
        self.assertEqual(r.verdict, "failing-psi")
        self.assertAlmostEqual(r.psi_score_distribution, 0.40)
        self.assertFalse(r.ready)

    def test_ready(self):
        runs = [
            FakeShadowRun(students_scored=300, band_changes=20, agreement_pct=0.93, psi_score_distribution=0.05),
            FakeShadowRun(students_scored=200, band_changes=10, agreement_pct=0.91, psi_score_distribution=0.07),
        ]
        with _patched_models(
            production=FakeArtifact("v1"),
            candidate=FakeArtifact("v2"),
            shadow_runs=runs,
        ):
            r = compute_readiness(min_students=100, min_agreement=0.85, max_psi=0.25)
        self.assertEqual(r.verdict, "ready")
        self.assertTrue(r.ready)
        self.assertEqual(r.students_scored, 500)
        # Weighted agreement: (300*0.93 + 200*0.91) / 500 = 0.922
        self.assertAlmostEqual(r.agreement_pct, 0.922, places=3)

    def test_weighted_metrics_handle_tiny_run(self):
        # A 1-student run with terrible agreement shouldn't sink a
        # 999-student run with great agreement.
        runs = [
            FakeShadowRun(students_scored=999, band_changes=50, agreement_pct=0.95, psi_score_distribution=0.05),
            FakeShadowRun(students_scored=1, band_changes=1, agreement_pct=0.0, psi_score_distribution=1.0),
        ]
        with _patched_models(
            production=FakeArtifact("v1"),
            candidate=FakeArtifact("v2"),
            shadow_runs=runs,
        ):
            r = compute_readiness()
        self.assertEqual(r.verdict, "ready")
        self.assertGreater(r.agreement_pct, 0.94)

    def test_none_agreement_in_run_is_skipped(self):
        # A run with no recorded agreement shouldn't break the weighted
        # average — it's just dropped from the denominator.
        runs = [
            FakeShadowRun(students_scored=100, band_changes=5, agreement_pct=0.92, psi_score_distribution=0.04),
            FakeShadowRun(students_scored=50, band_changes=2, agreement_pct=None, psi_score_distribution=None),
        ]
        with _patched_models(
            production=FakeArtifact("v1"),
            candidate=FakeArtifact("v2"),
            shadow_runs=runs,
        ):
            r = compute_readiness()
        self.assertEqual(r.verdict, "ready")
        self.assertAlmostEqual(r.agreement_pct, 0.92, places=3)
        self.assertAlmostEqual(r.psi_score_distribution, 0.04, places=3)

    def test_band_change_pct_uses_total_students(self):
        runs = [
            FakeShadowRun(students_scored=400, band_changes=80, agreement_pct=0.90, psi_score_distribution=0.05),
        ]
        with _patched_models(
            production=FakeArtifact("v1"),
            candidate=FakeArtifact("v2"),
            shadow_runs=runs,
        ):
            r = compute_readiness()
        self.assertAlmostEqual(r.band_change_pct, 0.20, places=3)

    def test_strict_threshold_combinations(self):
        # Raising thresholds turns a ready model into not-ready.
        runs = [
            FakeShadowRun(students_scored=200, band_changes=10, agreement_pct=0.86, psi_score_distribution=0.20),
        ]
        with _patched_models(
            production=FakeArtifact("v1"),
            candidate=FakeArtifact("v2"),
            shadow_runs=runs,
        ):
            ready = compute_readiness(min_agreement=0.85, max_psi=0.25)
            self.assertEqual(ready.verdict, "ready")
            tighter = compute_readiness(min_agreement=0.90, max_psi=0.25)
            self.assertEqual(tighter.verdict, "failing-agreement")

    def test_no_production_does_not_block_readiness(self):
        # A first-ever promotion (no production yet) is allowed when
        # shadow evidence supports it.
        runs = [
            FakeShadowRun(students_scored=200, band_changes=10, agreement_pct=0.95, psi_score_distribution=0.05),
        ]
        with _patched_models(
            production=None,
            candidate=FakeArtifact("v1"),
            shadow_runs=runs,
        ):
            r = compute_readiness()
        self.assertEqual(r.verdict, "ready")
        self.assertIsNone(r.production_version)
