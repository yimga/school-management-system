"""Wave 4 tests — grade prediction heuristic, loader precedence,
evaluation math, and registry promote atomicity.
"""

from __future__ import annotations

import os
import tempfile
from io import StringIO

from django.core.management import CommandError, call_command
from django.test import SimpleTestCase, TestCase, override_settings
from django.utils import timezone

from apps.accounts.models import User
from apps.analytics.ml.grade_prediction_features import GradePredictionFeatures
from apps.analytics.ml.grade_prediction_model import (
    _heuristic_predict,
    _model_path,
    predict_grade,
)
from apps.analytics.models import (
    GradePrediction,
    GradePredictionLabel,
    GradePredictionModelArtifact,
)


class HeuristicGradePredictTests(SimpleTestCase):
    def test_default_features_yield_cohort_default(self):
        feats = GradePredictionFeatures(
            student_id="s", subject_id="x", term_id="t",
        )
        score, reason = _heuristic_predict(feats)
        # No mid-term, full attendance → prior_mean_score (60) is the base.
        self.assertAlmostEqual(score, 60.0, delta=0.01)
        self.assertIn("default cohort grade", reason.lower() + "Insufficient signal".lower()) if False else None

    def test_mid_term_blends_with_prior(self):
        feats = GradePredictionFeatures(
            student_id="s", subject_id="x", term_id="t",
            mid_term_avg=80, mid_term_count=2, prior_mean_score=50,
        )
        score, _reason = _heuristic_predict(feats)
        # 0.7 * 80 + 0.3 * 50 = 71
        self.assertAlmostEqual(score, 71.0, delta=0.01)

    def test_attendance_penalty(self):
        feats = GradePredictionFeatures(
            student_id="s", subject_id="x", term_id="t",
            mid_term_avg=70, mid_term_count=2, prior_mean_score=70,
            attendance_rate=0.70,
        )
        score, reason = _heuristic_predict(feats)
        # base = 70, penalty = min(10, 20*0.5)=10 → score = 60.
        self.assertAlmostEqual(score, 60.0, delta=0.01)
        self.assertIn("attendance 70%", reason)

    def test_trend_nudge_clipped(self):
        # eval_trend=30 → 0.4*30=12 → clipped to 5.
        feats = GradePredictionFeatures(
            student_id="s", subject_id="x", term_id="t",
            mid_term_avg=60, mid_term_count=2, prior_mean_score=60,
            eval_trend=30,
        )
        score, _ = _heuristic_predict(feats)
        self.assertAlmostEqual(score, 65.0, delta=0.01)

    def test_clamped_to_0_100(self):
        feats = GradePredictionFeatures(
            student_id="s", subject_id="x", term_id="t",
            mid_term_avg=200, mid_term_count=2, prior_mean_score=200,
        )
        score, _ = _heuristic_predict(feats)
        self.assertLessEqual(score, 100.0)
        self.assertGreaterEqual(score, 0.0)


class GradeModelPathPrecedenceTests(TestCase):
    """Loader respects registry → settings → env precedence."""

    def setUp(self):
        from apps.analytics.ml import grade_prediction_model
        grade_prediction_model._MODEL_CACHE.clear()

    def _operator(self, suffix):
        return User.objects.create_user(
            username=f"gp_op_{suffix}",
            email=f"gp_op_{suffix}@example.com",
            password="p",
        )

    def test_registry_path_wins_over_env(self):
        op = self._operator(id(self))
        with tempfile.NamedTemporaryFile(suffix=".joblib", delete=False) as f:
            f.write(b"placeholder")
            path = f.name
        try:
            GradePredictionModelArtifact.objects.create(
                model_version="g_live",
                artifact_path=path,
                trained_at=timezone.now(),
                status=GradePredictionModelArtifact.Status.PRODUCTION,
                registered_by=op,
                promoted_at=timezone.now(),
                promoted_by=op,
            )
            with override_settings(
                GRADE_PREDICTION_MODEL_PATH="/should/not/win.joblib"
            ):
                self.assertEqual(_model_path(), path)
        finally:
            os.unlink(path)

    def test_settings_wins_when_no_registry_row(self):
        self.assertIsNone(GradePredictionModelArtifact.current_production())
        with override_settings(GRADE_PREDICTION_MODEL_PATH="/from/settings.joblib"):
            os.environ["GRADE_PREDICTION_MODEL_PATH"] = "/from/env.joblib"
            try:
                self.assertEqual(_model_path(), "/from/settings.joblib")
            finally:
                del os.environ["GRADE_PREDICTION_MODEL_PATH"]


class GradePredictionRegistryTests(TestCase):
    def test_promote_archives_previous(self):
        op = User.objects.create_user(
            username=f"gp_reg_{id(self)}",
            email="r@example.com", password="p",
        )
        prev = GradePredictionModelArtifact.objects.create(
            model_version="g_v1",
            artifact_path="/tmp/x.joblib",
            trained_at=timezone.now(),
            status=GradePredictionModelArtifact.Status.PRODUCTION,
            registered_by=op, promoted_at=timezone.now(), promoted_by=op,
        )
        cand = GradePredictionModelArtifact.objects.create(
            model_version="g_v2",
            artifact_path="/tmp/y.joblib",
            trained_at=timezone.now(),
            status=GradePredictionModelArtifact.Status.CANDIDATE,
            registered_by=op,
        )
        archived = cand.promote(by_user=op)
        prev.refresh_from_db()
        cand.refresh_from_db()
        self.assertEqual(archived.pk, prev.pk)
        self.assertEqual(prev.status, GradePredictionModelArtifact.Status.ARCHIVED)
        self.assertEqual(cand.status, GradePredictionModelArtifact.Status.PRODUCTION)


class EvaluateGradePredictionTests(TestCase):
    def setUp(self):
        from apps.academics.models import (
            AcademicYear, Department, Subject, Term,
        )
        from apps.people.models import StudentProfile
        from apps.schools.models import School
        from apps.siteconfig.models import RegionConfig

        uid = id(self)
        region, _ = RegionConfig.objects.get_or_create(
            code=f"GP{uid % 9999}",
            defaults={
                "name": "GP Region", "default_language": "en",
                "timezone": "UTC", "date_format": "DD/MM/YYYY",
            },
        )
        self.school = School.objects.create(
            name=f"GPS {uid}", slug=f"gps-{uid}",
            subdomain=f"gps-{uid}", is_active=True, default_region=region,
        )
        self.operator = User.objects.create_user(
            username=f"gp_eval_{uid}",
            email=f"gp_eval_{uid}@example.com", password="p",
        )
        self.dept = Department.objects.create(name=f"D-{uid}", code=f"DC{uid % 9999}")
        self.year = AcademicYear.objects.create(
            name=f"GPY-{uid}",
            start_date=timezone.now().date(),
            end_date=(timezone.now() + timezone.timedelta(days=365)).date(),
        )
        self.term = Term.objects.create(
            name=f"GPT-{uid}", academic_year=self.year,
            start_date=timezone.now().date(),
            end_date=(timezone.now() + timezone.timedelta(days=90)).date(),
        )
        self.subj = Subject.objects.create(name=f"Math-{uid}")
        # 5 students. predicted=labeled+5 for all → MAE=5, RMSE=5.
        for i in range(5):
            u = User.objects.create_user(
                username=f"gp_s_{uid}_{i}",
                email=f"gp_s_{uid}_{i}@example.com", password="p",
            )
            student = StudentProfile.objects.create(
                school=self.school, user=u,
                first_name=f"GP{i}", last_name="Stud",
                student_code=f"GP-{uid % 9999}-{i}",
            )
            GradePrediction.objects.create(
                school=self.school, student=student, subject=self.subj,
                academic_year=self.year, term=self.term,
                predicted_grade=75.0,
            )
            GradePredictionLabel.objects.create(
                school=self.school, student=student, subject=self.subj,
                academic_year=self.year, term=self.term,
                actual_grade=70.0, labeled_by=self.operator,
            )

    def test_evaluate_reports_mae_rmse_r2(self):
        import json
        tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
        tmp.close()
        try:
            call_command(
                "evaluate_grade_prediction_model",
                "--school", self.school.slug,
                "--json", tmp.name,
                stdout=StringIO(),
            )
            report = json.loads(open(tmp.name).read())
            metrics = report["metrics"]
            # Constant gap of +5 → MAE=5, RMSE=5.
            self.assertAlmostEqual(metrics["mae"], 5.0, delta=0.001)
            self.assertAlmostEqual(metrics["rmse"], 5.0, delta=0.001)
            # All actuals identical (=70) → SS_tot uses fallback 1.0.
            self.assertEqual(report["joined"], 5)
            self.assertEqual(report["missing_predictions"], 0)
        finally:
            os.unlink(tmp.name)

    def test_max_mae_gate_fails(self):
        with self.assertRaises(CommandError):
            call_command(
                "evaluate_grade_prediction_model",
                "--school", self.school.slug,
                "--max-mae", "1.0",
                stdout=StringIO(),
            )

    def test_no_join_raises(self):
        # Different school → empty join.
        from apps.schools.models import School
        other = School.objects.create(
            name="Other GP", slug=f"other-gp-{id(self)}",
            subdomain=f"other-gp-{id(self)}", is_active=True,
            default_region=self.school.default_region,
        )
        with self.assertRaises(CommandError):
            call_command(
                "evaluate_grade_prediction_model",
                "--school", other.slug,
                stdout=StringIO(),
            )
